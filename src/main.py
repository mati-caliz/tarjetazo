"""Orquestador: revisa el mail, parsea el resumen de BNA, categoriza y manda Telegram.
Pensado para correr periódicamente vía systemd timer / cron."""
import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from categorize import categorizar_movimientos
from email_client import buscar_ultimo_resumen_no_leido, marcar_como_leido
from formatter import formatear_resumen
from historico import cargar_historico, guardar_historico, periodo_anterior, registrar_periodo
from pdf_parser import extraer_movimientos, extraer_periodo, extraer_saldo_actual
from telegram_bot import enviar_mensaje

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tarjetazo")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ESTADO_PATH = os.path.join(DATA_DIR, "ultimo_procesado.txt")
COMERCIOS_CONOCIDOS_PATH = os.path.join(DATA_DIR, "comercios_conocidos.json")
ULTIMO_EXITO_PATH = os.path.join(DATA_DIR, "ultimo_exito.txt")
ALERTA_SILENCIO_PATH = os.path.join(DATA_DIR, "alerta_silencio_enviada.txt")

DIAS_ALERTA_SILENCIO = 40
TOLERANCIA_SALDO = 1.0  # pesos de margen por redondeo


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


def _marcar_exito() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ULTIMO_EXITO_PATH, "w") as f:
        f.write(datetime.now().isoformat())
    if os.path.exists(ALERTA_SILENCIO_PATH):
        os.remove(ALERTA_SILENCIO_PATH)


def _chequear_silencio() -> None:
    """Si hace mucho que no se procesa un resumen nuevo, avisa que el bot podría
    estar roto (mail sin acceso, sesión de Claude vencida, etc.) en vez de quedarse
    en silencio indefinidamente. Solo manda la alerta una vez por episodio."""
    if not os.path.exists(ULTIMO_EXITO_PATH):
        return  # primera corrida, todavía no hay base de comparación

    with open(ULTIMO_EXITO_PATH) as f:
        ultimo = datetime.fromisoformat(f.read().strip())

    dias = (datetime.now() - ultimo).days
    if dias >= DIAS_ALERTA_SILENCIO and not os.path.exists(ALERTA_SILENCIO_PATH):
        log.warning("Hace %d días que no se procesa un resumen nuevo.", dias)
        enviar_mensaje(
            f"⚠️ Hace {dias} días que Tarjetazo no procesa un resumen nuevo de BNA. "
            "Puede ser normal (todavía no cerró el mes) o puede que el bot esté roto "
            "(revisar credenciales de mail o la sesión de Claude Code en el VPS)."
        )
        os.makedirs(DATA_DIR, exist_ok=True)
        open(ALERTA_SILENCIO_PATH, "w").close()


def main() -> None:
    pdf_password = os.environ["PDF_PASSWORD"]

    log.info("Buscando resumen no leído de BNA...")
    resultado = buscar_ultimo_resumen_no_leido()
    if resultado is None:
        log.info("No hay resumen nuevo. Nada que hacer.")
        _chequear_silencio()
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

    saldo_pesos, _saldo_dolar = extraer_saldo_actual(pdf_bytes, pdf_password)
    total_calculado = sum(m.pesos for m in movimientos)
    advertencia = None
    if abs(total_calculado - saldo_pesos) > TOLERANCIA_SALDO:
        advertencia = (
            f"El total calculado ({total_calculado:,.2f}) no coincide con el saldo "
            f"del resumen ({saldo_pesos:,.2f}). Puede que el parser se haya perdido "
            "algún movimiento — revisar el PDF a mano."
        )
        log.warning(advertencia)

    log.info("Categorizando %d movimientos...", len(movimientos))
    detalles = [m.detalle for m in movimientos]
    conocidos = _cargar_comercios_conocidos()
    info = categorizar_movimientos(detalles, conocidos)

    historico = cargar_historico()
    anterior = periodo_anterior(historico)

    log.info("Formateando y enviando mensaje...")
    mensaje = formatear_resumen(movimientos, info, periodo, anterior=anterior, advertencia=advertencia)
    enviar_mensaje(mensaje)

    # Solo se persiste el estado (comercios aprendidos, histórico, mail leído, resumen
    # procesado) una vez que el envío a Telegram salió bien, para no perder el resumen
    # del mes si algo falla antes de este punto.
    _guardar_comercios_conocidos(conocidos)

    por_categoria_totales: dict[str, float] = {}
    for m in movimientos:
        cat = info.get(m.detalle, {}).get("categoria", "Otros")
        por_categoria_totales[cat] = por_categoria_totales.get(cat, 0.0) + m.pesos
    registrar_periodo(historico, periodo, total_calculado, sum(m.dolar for m in movimientos), por_categoria_totales)
    guardar_historico(historico)

    _marcar_procesado(message_id)
    _marcar_exito()
    marcar_como_leido(uid)
    log.info("Listo. Resumen enviado por Telegram.")


if __name__ == "__main__":
    main()
