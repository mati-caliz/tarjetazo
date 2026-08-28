"""Envío de mensajes de Tarjetazo mediante la API de Respondi."""
import html
import os
import re
import time

import requests

LIMITE_TELEGRAM = 4096
TIMEOUT_HTTP_SEGUNDOS = 15
TIMEOUT_ENTREGA_SEGUNDOS = 60
INTERVALO_ENTREGA_SEGUNDOS = 0.5
ESTADOS_ENTREGADOS = {"sent", "delivered", "read"}
ETIQUETAS_HTML = re.compile(r"</?b>", re.IGNORECASE)


def _texto_plano(texto: str) -> str:
    return html.unescape(ETIQUETAS_HTML.sub("", texto))


def _partir_linea(linea: str, limite: int) -> list[str]:
    if len(linea) <= limite:
        return [linea]
    return [linea[inicio : inicio + limite] for inicio in range(0, len(linea), limite)]


def _partir_en_bloques(texto: str, limite: int = LIMITE_TELEGRAM) -> list[str]:
    bloques: list[str] = []
    actual = ""
    for linea_original in _texto_plano(texto).split("\n"):
        for linea in _partir_linea(linea_original, limite):
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


def _esperar_entrega(api_url: str, api_key: str, message_id: str) -> None:
    limite = time.monotonic() + TIMEOUT_ENTREGA_SEGUNDOS
    headers = {"Authorization": f"Bearer {api_key}"}

    while time.monotonic() < limite:
        respuesta = requests.get(
            f"{api_url}/v1/messages/{message_id}",
            headers=headers,
            timeout=TIMEOUT_HTTP_SEGUNDOS,
        )
        respuesta.raise_for_status()
        estado = respuesta.json().get("deliveryStatus")
        if estado in ESTADOS_ENTREGADOS:
            return
        if estado == "failed":
            raise RuntimeError(f"Respondi no pudo entregar el mensaje {message_id}")
        time.sleep(INTERVALO_ENTREGA_SEGUNDOS)

    raise TimeoutError(f"Respondi no confirmó la entrega del mensaje {message_id}")


def enviar_mensaje(texto: str) -> None:
    api_url = os.environ["RESPONDI_API_URL"].rstrip("/")
    api_key = os.environ["RESPONDI_API_KEY"]
    channel_id = os.environ["RESPONDI_CHANNEL_ID"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    headers = {"Authorization": f"Bearer {api_key}"}

    for bloque in _partir_en_bloques(texto):
        respuesta = requests.post(
            f"{api_url}/v1/messages/send",
            headers=headers,
            json={
                "channelId": channel_id,
                "to": chat_id,
                "content": {"type": "text", "text": bloque},
            },
            timeout=TIMEOUT_HTTP_SEGUNDOS,
        )
        respuesta.raise_for_status()
        message_id = respuesta.json().get("messageId")
        if not isinstance(message_id, str) or not message_id:
            raise RuntimeError("Respondi no devolvió el identificador del mensaje")
        _esperar_entrega(api_url, api_key, message_id)
