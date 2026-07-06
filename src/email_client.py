"""Busca en la casilla de Outlook/Hotmail el último resumen de BNA no procesado
y devuelve el PDF adjunto."""
import email
import imaplib
import os
from email.message import Message

IMAP_HOST = "outlook.office365.com"
REMITENTE_BNA = "NAVI@mailing.bna.com.ar"


def _extraer_pdf(msg: Message) -> bytes | None:
    for part in msg.walk():
        filename = part.get_filename()
        if filename and filename.lower().endswith(".pdf"):
            return part.get_payload(decode=True)
    return None


def buscar_ultimo_resumen_no_leido() -> tuple[bytes, str] | None:
    """Devuelve (pdf_bytes, message_id) del resumen de BNA no leído más reciente, o None."""
    user = os.environ["EMAIL_USER"]
    password = os.environ["EMAIL_APP_PASSWORD"]

    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(user, password)
        imap.select("INBOX")

        status, data = imap.search(None, f'(UNSEEN FROM "{REMITENTE_BNA}")')
        if status != "OK" or not data[0]:
            return None

        ids = data[0].split()
        ultimo_id = ids[-1]  # el más reciente

        status, msg_data = imap.fetch(ultimo_id, "(RFC822)")
        if status != "OK":
            return None

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        message_id = msg.get("Message-ID", ultimo_id.decode())

        pdf_bytes = _extraer_pdf(msg)
        if not pdf_bytes:
            return None

        imap.store(ultimo_id, "+FLAGS", "\\Seen")
        return pdf_bytes, message_id
