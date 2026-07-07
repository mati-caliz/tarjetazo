"""Envío de mensajes por Telegram usando el Bot API (HTTP simple, sin SDK)."""
import os

import requests

API_BASE = "https://api.telegram.org"
LIMITE_TELEGRAM = 4096


def _partir_en_bloques(texto: str, limite: int = LIMITE_TELEGRAM) -> list[str]:
    """Parte el texto en bloques que no superen el límite de Telegram, cortando
    solo entre líneas completas (nunca a mitad de una etiqueta HTML)."""
    bloques: list[str] = []
    actual = ""
    for linea in texto.split("\n"):
        candidato = f"{actual}\n{linea}" if actual else linea
        if len(candidato) > limite:
            if actual:
                bloques.append(actual)
            actual = linea
        else:
            actual = candidato
    if actual:
        bloques.append(actual)
    return bloques


def enviar_mensaje(texto: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    for bloque in _partir_en_bloques(texto):
        resp = requests.post(
            f"{API_BASE}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": bloque, "parse_mode": "HTML"},
            timeout=15,
        )
        resp.raise_for_status()
