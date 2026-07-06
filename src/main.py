"""Orquestador: revisa el mail, parsea el resumen de BNA, categoriza y manda Telegram.
Pensado para correr periódicamente vía systemd timer / cron."""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from categorize import categorizar_movimientos
from email_client import buscar_ultimo_resumen_no_leido
from formatter import formatear_resumen
from pdf_parser import extraer_movimientos, extraer_periodo
from telegram_bot import enviar_mensaje

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tarjetazo")

ESTADO_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ultimo_procesado.txt")


def _ya_procesado(message_id: str) -> bool:
    if not os.path.exists(ESTADO_PATH):
        return False
    with open(ESTADO_PATH) as f:
        return f.read().strip() == message_id


def _marcar_procesado(message_id: str) -> None:
    with open(ESTADO_PATH, "w") as f:
        f.write(message_id)


def main() -> None:
    pdf_password = os.environ["PDF_PASSWORD"]

    log.info("Buscando resumen no leído de BNA...")
    resultado = buscar_ultimo_resumen_no_leido()
    if resultado is None:
        log.info("No hay resumen nuevo. Nada que hacer.")
        return

    pdf_bytes, message_id = resultado

    if _ya_procesado(message_id):
        log.info("Este resumen ya fue procesado antes. Nada que hacer.")
        return

    log.info("Parseando PDF...")
    movimientos = extraer_movimientos(pdf_bytes, pdf_password)
    periodo = extraer_periodo(pdf_bytes, pdf_password)

    if not movimientos:
        log.warning("No se encontraron movimientos en el PDF. Revisar formato.")
        return

    log.info("Categorizando %d movimientos...", len(movimientos))
    detalles = [m.detalle for m in movimientos]
    categorias = categorizar_movimientos(detalles)

    log.info("Formateando y enviando mensaje...")
    mensaje = formatear_resumen(movimientos, categorias, periodo)
    enviar_mensaje(mensaje)

    _marcar_procesado(message_id)
    log.info("Listo. Resumen enviado por Telegram.")


if __name__ == "__main__":
    main()
