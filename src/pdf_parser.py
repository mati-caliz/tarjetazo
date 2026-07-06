"""Extrae los movimientos del resumen de tarjeta VISA BNA (PDF con clave)."""
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

import pikepdf
import pdfplumber

LINE_RE = re.compile(
    r"^(?P<fecha>\d{2}\.\d{2}\.\d{2})\s+"
    r"(?:(?P<comprobante>\d{6})\s+)?"
    r"(?P<detalle>.+?)\s+"
    r"(?P<pesos>-?[\d.]+,\d{2})\s+"
    r"(?P<dolar>-?[\d.]+,\d{2})$"
)

# Líneas que matchean el patrón pero son resúmenes/totales, no consumos reales.
IGNORAR_DETALLE = re.compile(
    r"^(SU PAGO|TOTAL CONSUMOS|SALDO ACTUAL|SALDO ANTERIOR)", re.IGNORECASE
)


@dataclass
class Movimiento:
    fecha: datetime
    comprobante: str | None
    detalle: str
    pesos: float
    dolar: float


def _parse_monto(raw: str) -> float:
    return float(raw.replace(".", "").replace(",", "."))


def extraer_movimientos(pdf_bytes: bytes, password: str) -> list[Movimiento]:
    with pikepdf.open(BytesIO(pdf_bytes), password=password) as decrypted:
        buf = BytesIO()
        decrypted.save(buf)
        buf.seek(0)

    movimientos: list[Movimiento] = []
    with pdfplumber.open(buf) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                m = LINE_RE.match(line.strip())
                if not m:
                    continue
                detalle = m.group("detalle").strip()
                if IGNORAR_DETALLE.match(detalle):
                    continue
                fecha = datetime.strptime(m.group("fecha"), "%d.%m.%y")
                movimientos.append(
                    Movimiento(
                        fecha=fecha,
                        comprobante=m.group("comprobante"),
                        detalle=detalle,
                        pesos=_parse_monto(m.group("pesos")),
                        dolar=_parse_monto(m.group("dolar")),
                    )
                )
    return movimientos


def extraer_periodo(pdf_bytes: bytes, password: str) -> str:
    """Devuelve el identificador de cierre (ej. '11 Jun 26') para deduplicar resúmenes."""
    with pikepdf.open(BytesIO(pdf_bytes), password=password) as decrypted:
        buf = BytesIO()
        decrypted.save(buf)
        buf.seek(0)

    with pdfplumber.open(buf) as pdf:
        text = pdf.pages[0].extract_text() or ""
    m = re.search(r"CIERRE ACTUAL:\s*(\d{2} \w{3} \d{2})", text)
    return m.group(1) if m else "desconocido"
