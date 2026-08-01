import imaplib
import re
import smtplib
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from config import FirmConfig
from intake import Incoming


def build_reply(incoming: Incoming, draft: str, config: FirmConfig) -> EmailMessage:
    message = EmailMessage()
    message["From"] = config.mailbox.user or config.firm_name
    message["To"] = incoming.sender_email or ""
    subject = incoming.subject or "your enquiry"
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    if incoming.message_id:
        message["In-Reply-To"] = incoming.message_id
        message["References"] = incoming.message_id
    message.set_content(draft)
    return message


def build_alert(incoming: Incoming, reasons: list[str], config: FirmConfig, enquiry_id: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = config.mailbox.user or config.firm_name
    message["To"] = config.approver_email or config.mailbox.user
    message["Subject"] = f"{config.escalation_subject_prefix} {incoming.subject or '(no subject)'}"
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    sender = incoming.sender_name or incoming.sender_email or "unknown sender"
    lines = [
        f"Enquiry {enquiry_id} needs a person.",
        f"From: {sender}",
        f"Received: {incoming.received_at}",
        "",
        "Reasons:",
        *[f"  - {reason}" for reason in reasons],
        "",
        "Original enquiry:",
        incoming.body[:2000],
    ]
    message.set_content("\n".join(lines))
    return message


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")[:60]


class LocalDelivery:
    def __init__(self, outbox_dir: Path) -> None:
        self.drafts_dir = outbox_dir / "drafts"
        self.escalations_dir = outbox_dir / "escalations"
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.escalations_dir.mkdir(parents=True, exist_ok=True)

    def deliver_draft(self, incoming: Incoming, draft: str, config: FirmConfig, enquiry_id: str) -> str:
        message = build_reply(incoming, draft, config)
        path = self.drafts_dir / f"{enquiry_id}-{safe_name(incoming.subject or 'enquiry')}.eml"
        path.write_bytes(bytes(message))
        return str(path)

    def deliver_alert(self, incoming: Incoming, reasons: list[str], config: FirmConfig, enquiry_id: str) -> str:
        message = build_alert(incoming, reasons, config, enquiry_id)
        path = self.escalations_dir / f"{enquiry_id}-ESCALATION.eml"
        path.write_bytes(bytes(message))
        return str(path)


class ImapDelivery:
    def __init__(self, config: FirmConfig) -> None:
        self.config = config

    def deliver_draft(self, incoming: Incoming, draft: str, config: FirmConfig, enquiry_id: str) -> str:
        mailbox = config.mailbox
        message = build_reply(incoming, draft, config)
        with imaplib.IMAP4_SSL(mailbox.host) as imap:
            imap.login(mailbox.user, mailbox.password)
            imap.append(
                f'"{mailbox.drafts_folder}"',
                r"(\Draft)",
                imaplib.Time2Internaldate(time.time()),
                bytes(message),
            )
        return f"IMAP draft in {mailbox.drafts_folder}"

    def deliver_alert(self, incoming: Incoming, reasons: list[str], config: FirmConfig, enquiry_id: str) -> str:
        mailbox = config.mailbox
        message = build_alert(incoming, reasons, config, enquiry_id)
        recipient = config.approver_email or mailbox.user
        with smtplib.SMTP(mailbox.smtp_host, mailbox.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(mailbox.user, mailbox.password)
            smtp.send_message(message, from_addr=mailbox.user, to_addrs=[recipient])
        return f"alert sent to {recipient}"
