import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKER_DIR = HERE.parent
SYSTEM_PROMPT_FILE = WORKER_DIR / "system-prompt.md"
FOLLOWUP_PROMPT_FILE = WORKER_DIR / "followup-prompt.md"
CONFIG_FILE = HERE / "firm-config.json"
DB_FILE = HERE / "state" / "enquiries.db"
LOCAL_INBOX = HERE / "inbox"
LOCAL_OUTBOX = HERE / "outbox"


@dataclass
class Mailbox:
    host: str = "imap.gmail.com"
    user: str = ""
    inbox_folder: str = "INBOX"
    drafts_folder: str = "[Gmail]/Drafts"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    @property
    def password(self) -> str:
        return os.environ.get("IMAP_APP_PASSWORD", "")


@dataclass
class FirmConfig:
    firm_name: str = "[Firm]"
    firm_phone: str = "[phone]"
    booking_link: str = "[booking link]"
    known_clients: list[str] = field(default_factory=list)
    declined_streams: list[str] = field(default_factory=list)
    referral_policy: str = "do not refer out"
    fee_policy: str = "no quotes in writing"
    language_policy: str = "reply in the enquiry's language"
    approver_email: str = ""
    escalation_subject_prefix: str = "[URGENT — enquiry desk]"
    mailbox: Mailbox = field(default_factory=Mailbox)
    poll_seconds: int = 90
    brain: str = "cli"
    api_model: str = "claude-haiku-4-5"

    def placeholders(self) -> dict[str, str]:
        return {
            "{{FIRM_NAME}}": self.firm_name,
            "{{FIRM_PHONE}}": self.firm_phone,
            "{{BOOKING_LINK}}": self.booking_link,
            "{{KNOWN_CLIENTS}}": ", ".join(self.known_clients) or "(none)",
            "{{DECLINED_STREAMS}}": ", ".join(self.declined_streams) or "(none declared)",
            "{{REFERRAL_POLICY}}": self.referral_policy,
            "{{FEE_POLICY}}": self.fee_policy,
            "{{LANGUAGE_POLICY}}": self.language_policy,
        }


def load_config(path: Path = CONFIG_FILE) -> FirmConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    mailbox = Mailbox(**raw.pop("mailbox", {}))
    known = [str(c) for c in raw.pop("known_clients", [])]
    declined = [str(s) for s in raw.pop("declined_streams", [])]
    allowed = {f.name for f in FirmConfig.__dataclass_fields__.values()}
    clean = {k: v for k, v in raw.items() if k in allowed}
    return FirmConfig(mailbox=mailbox, known_clients=known, declined_streams=declined, **clean)


def load_prompt(path: Path, config: FirmConfig) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"---PROMPT-START---\n(.*?)\n---PROMPT-END---", text, re.DOTALL)
    if match is None:
        raise SystemExit(f"Prompt markers not found in {path}")
    prompt = match.group(1)
    for placeholder, value in config.placeholders().items():
        prompt = prompt.replace(placeholder, value)
    return prompt.replace("{{TODAY}}", date.today().isoformat())
