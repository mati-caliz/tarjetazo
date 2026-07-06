"""Envío de mensajes por Telegram usando el Bot API (HTTP simple, sin SDK)."""
import os

import requests

API_BASE = "https://api.telegram.org"


def enviar_mensaje(texto: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    resp = requests.post(
        f"{API_BASE}/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"},
        timeout=15,
    )
    resp.raise_for_status()
