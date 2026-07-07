"""Busca en la casilla (Gmail) el último resumen de BNA no procesado y devuelve el PDF.

El mail original de BNA (NAVI@mailing.bna.com.ar) se reenvía/redirige desde Outlook a
esta casilla de Gmail mediante una regla. Leemos vía IMAP con app password de Gmail
(Outlook ya no acepta app passwords por IMAP desde sep-2024)."""
import email
import imaplib
import os
from email.message import Message

IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
REMITENTE_BNA = "NAVI@mailing.bna.com.ar"


def _extraer_pdf(msg: Message) -> bytes | None:
    for part in msg.walk():
        filename = part.get_filename()
        if filename and filename.lower().endswith(".pdf"):
            return part.get_payload(decode=True)
    return None


def buscar_ultimo_resumen_no_leido() -> tuple[bytes, str, str] | None:
    """Devuelve (pdf_bytes, message_id, uid) del resumen de BNA no leído más reciente, o None.

    A propósito NO marca el mail como leído acá: eso lo hace `marcar_como_leido`
    una vez que el resto del pipeline (parseo, categorización, envío a Telegram)
    terminó con éxito. Si se marcara acá y algo fallara después, el mail quedaría
    leído sin que el resumen se haya llegado a mandar, y se perdería ese mes."""
    user = os.environ["EMAIL_USER"]
    password = os.environ["EMAIL_APP_PASSWORD"]

    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(user, password)
        imap.select("INBOX")

        # TEXT matchea el remitente de BNA tanto si la regla de Outlook preserva el
        # From (redirect) como si lo deja embebido en el cuerpo (forward). El PDF +
        # la clave (DNI) actúan de segundo filtro aguas abajo.
        status, data = imap.search(None, f'(UNSEEN TEXT "{REMITENTE_BNA}")')
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

        return pdf_bytes, message_id, ultimo_id.decode()


def marcar_como_leido(uid: str) -> None:
    user = os.environ["EMAIL_USER"]
    password = os.environ["EMAIL_APP_PASSWORD"]

    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(user, password)
        imap.select("INBOX")
        imap.store(uid.encode(), "+FLAGS", "\\Seen")
