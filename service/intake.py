import email
import email.header
import email.utils
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime
from email.message import Message
from pathlib import Path

from config import FirmConfig


@dataclass
class Incoming:
    message_id: str
    sender_name: str | None
    sender_email: str | None
    subject: str | None
    body: str
    received_at: str
    channel: str = "email"


def decode_header(value: str | None) -> str | None:
    if value is None:
        return None
    parts = email.header.decode_header(value)
    out: list[str] = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out).strip() or None


def strip_html(html: str) -> str:
    text = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", text)).strip()


def extract_body(message: Message) -> str:
    if message.is_multipart():
        plain: str | None = None
        html: str | None = None
        for part in message.walk():
            if part.get_content_maintype() != "text" or part.get("Content-Disposition", "").startswith("attachment"):
                continue
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if part.get_content_subtype() == "plain" and plain is None:
                plain = text
            elif part.get_content_subtype() == "html" and html is None:
                html = text
        if plain:
            return plain.strip()
        if html:
            return strip_html(html)
        return ""
    payload = message.get_payload(decode=True)
    if isinstance(payload, bytes):
        charset = message.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
    else:
        text = str(message.get_payload())
    if message.get_content_subtype() == "html":
        return strip_html(text)
    return text.strip()


def parse_message(message: Message, fallback_id: str) -> Incoming:
    sender_name, sender_email = email.utils.parseaddr(str(message.get("From", "")))
    received = message.get("Date")
    if received:
        try:
            received_at = email.utils.parsedate_to_datetime(received).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            received_at = datetime.now().isoformat(timespec="seconds")
    else:
        received_at = datetime.now().isoformat(timespec="seconds")
    return Incoming(
        message_id=str(message.get("Message-ID", "")).strip() or fallback_id,
        sender_name=decode_header(sender_name) or None,
        sender_email=sender_email or None,
        subject=decode_header(message.get("Subject")),
        body=extract_body(message),
        received_at=received_at,
    )


class LocalIntake:
    def __init__(self, inbox_dir: Path) -> None:
        self.inbox_dir = inbox_dir
        self.processed_dir = inbox_dir / "processed"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self) -> list[Incoming]:
        items: list[Incoming] = []
        for path in sorted(self.inbox_dir.glob("*")):
            if not path.is_file() or path.suffix.lower() not in (".eml", ".txt"):
                continue
            fallback_id = f"<local-{path.name}>"
            if path.suffix.lower() == ".eml":
                message = email.message_from_bytes(path.read_bytes())
                incoming = parse_message(message, fallback_id)
            else:
                incoming = Incoming(
                    message_id=fallback_id,
                    sender_name=None,
                    sender_email=None,
                    subject=path.stem.replace("-", " "),
                    body=path.read_text(encoding="utf-8").strip(),
                    received_at=datetime.now().isoformat(timespec="seconds"),
                )
            items.append(incoming)
            path.rename(self.processed_dir / path.name)
        return items


class ImapIntake:
    def __init__(self, config: FirmConfig) -> None:
        self.config = config

    def fetch(self) -> list[Incoming]:
        mailbox = self.config.mailbox
        if not mailbox.user or not mailbox.password:
            raise SystemExit("IMAP mode needs mailbox.user in firm-config.json and IMAP_APP_PASSWORD in the environment.")
        items: list[Incoming] = []
        with imaplib.IMAP4_SSL(mailbox.host) as imap:
            imap.login(mailbox.user, mailbox.password)
            imap.select(mailbox.inbox_folder)
            status, data = imap.search(None, "UNSEEN")
            if status != "OK":
                return items
            for num in data[0].split():
                status, fetched = imap.fetch(num, "(RFC822)")
                if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                    continue
                message = email.message_from_bytes(fetched[0][1])
                items.append(parse_message(message, f"<imap-{num.decode()}-{datetime.now().timestamp()}>"))
        return items
