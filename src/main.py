"""Orquestador: revisa el mail, parsea el resumen de BNA, categoriza y manda Telegram.
Pensado para correr periódicamente vía systemd timer / cron."""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from categorize import categorizar_movimientos
from email_client import buscar_ultimo_resumen_no_leido, marcar_como_leido
from formatter import formatear_resumen
from pdf_parser import extraer_movimientos, extraer_periodo
from telegram_bot import enviar_mensaje

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tarjetazo")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ESTADO_PATH = os.path.join(DATA_DIR, "ultimo_procesado.txt")
COMERCIOS_CONOCIDOS_PATH = os.path.join(DATA_DIR, "comercios_conocidos.json")


def _ya_procesado(message_id: str) -> bool:
    if not os.path.exists(ESTADO_PATH):
        return False
    with open(ESTADO_PATH) as f:
        return f.read().strip() == message_id


def _marcar_procesado(message_id: str) -> None:
    with open(ESTADO_PATH, "w") as f:
        f.write(message_id)


def _cargar_comercios_conocidos() -> dict[str, dict[str, str]]:
    if not os.path.exists(COMERCIOS_CONOCIDOS_PATH):
        return {}
    with open(COMERCIOS_CONOCIDOS_PATH) as f:
        return json.load(f)


def _guardar_comercios_conocidos(conocidos: dict[str, dict[str, str]]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(COMERCIOS_CONOCIDOS_PATH, "w") as f:
        json.dump(conocidos, f, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> None:
    pdf_password = os.environ["PDF_PASSWORD"]

    log.info("Buscando resumen no leído de BNA...")
    resultado = buscar_ultimo_resumen_no_leido()
    if resultado is None:
        log.info("No hay resumen nuevo. Nada que hacer.")
        return

    pdf_bytes, message_id, uid = resultado

    if _ya_procesado(message_id):
        log.info("Este resumen ya fue procesado antes. Nada que hacer.")
        marcar_como_leido(uid)
        return

    log.info("Parseando PDF...")
    movimientos = extraer_movimientos(pdf_bytes, pdf_password)
    periodo = extraer_periodo(pdf_bytes, pdf_password)

    if not movimientos:
        log.warning("No se encontraron movimientos en el PDF. Revisar formato.")
        return

    log.info("Categorizando %d movimientos...", len(movimientos))
    detalles = [m.detalle for m in movimientos]
    conocidos = _cargar_comercios_conocidos()
    info = categorizar_movimientos(detalles, conocidos)

    log.info("Formateando y enviando mensaje...")
    mensaje = formatear_resumen(movimientos, info, periodo)
    enviar_mensaje(mensaje)

    # Solo se persiste el estado (comercios aprendidos, mail leído, resumen procesado)
    # una vez que el envío a Telegram salió bien, para no perder el resumen del mes
    # si algo falla antes de este punto.
    _guardar_comercios_conocidos(conocidos)
    _marcar_procesado(message_id)
    marcar_como_leido(uid)
    log.info("Listo. Resumen enviado por Telegram.")


if __name__ == "__main__":
    main()
