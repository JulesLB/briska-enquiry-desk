import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS enquiries (
    id TEXT PRIMARY KEY,
    message_id TEXT UNIQUE,
    channel TEXT NOT NULL DEFAULT 'email',
    sender_name TEXT,
    sender_email TEXT,
    subject TEXT,
    body TEXT NOT NULL,
    language TEXT,
    bucket TEXT,
    confidence TEXT,
    stream TEXT,
    urgent INTEGER NOT NULL DEFAULT 0,
    escalate INTEGER NOT NULL DEFAULT 0,
    escalation_reasons TEXT NOT NULL DEFAULT '[]',
    guardrail_hits TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'new',
    draft TEXT,
    summary TEXT,
    next_action TEXT,
    received_at TEXT NOT NULL,
    processed_at TEXT,
    response_seconds REAL
);
CREATE TABLE IF NOT EXISTS touches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_id TEXT NOT NULL REFERENCES enquiries(id),
    at TEXT NOT NULL,
    type TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    body TEXT
);
CREATE INDEX IF NOT EXISTS idx_touches_enquiry ON touches(enquiry_id);
"""


class Store:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def seen(self, message_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM enquiries WHERE message_id = ?", (message_id,)
        ).fetchone()
        return row is not None

    def new_id(self) -> str:
        return f"E-{datetime.now().strftime('%y%m%d%H%M%S%f')[:-4]}"

    def insert_enquiry(
        self,
        enquiry_id: str,
        message_id: str | None,
        channel: str,
        sender_name: str | None,
        sender_email: str | None,
        subject: str | None,
        body: str,
        received_at: str,
    ) -> None:
        self.conn.execute(
            "INSERT INTO enquiries (id, message_id, channel, sender_name, sender_email,"
            " subject, body, received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (enquiry_id, message_id, channel, sender_name, sender_email, subject, body, received_at),
        )
        self.conn.commit()

    def record_result(
        self,
        enquiry_id: str,
        language: str,
        bucket: str,
        confidence: str,
        stream: str,
        urgent: bool,
        escalate: bool,
        escalation_reasons: list[str],
        guardrail_hits: list[str],
        status: str,
        draft: str | None,
        summary: str,
        next_action: str,
        response_seconds: float,
    ) -> None:
        self.conn.execute(
            "UPDATE enquiries SET language=?, bucket=?, confidence=?, stream=?, urgent=?,"
            " escalate=?, escalation_reasons=?, guardrail_hits=?, status=?, draft=?, summary=?,"
            " next_action=?, processed_at=?, response_seconds=? WHERE id=?",
            (
                language, bucket, confidence, stream, int(urgent), int(escalate),
                json.dumps(escalation_reasons, ensure_ascii=False),
                json.dumps(guardrail_hits, ensure_ascii=False),
                status, draft, summary, next_action,
                datetime.now().isoformat(timespec="seconds"), response_seconds, enquiry_id,
            ),
        )
        self.conn.commit()

    def add_touch(self, enquiry_id: str, touch_type: str, note: str = "", body: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO touches (enquiry_id, at, type, note, body) VALUES (?, ?, ?, ?, ?)",
            (enquiry_id, datetime.now().isoformat(timespec="seconds"), touch_type, note, body),
        )
        self.conn.commit()

    def set_status(self, enquiry_id: str, status: str) -> None:
        self.conn.execute("UPDATE enquiries SET status=? WHERE id=?", (status, enquiry_id))
        self.conn.commit()

    def enquiries_since(self, iso_start: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM enquiries WHERE received_at >= ? ORDER BY received_at DESC",
            (iso_start,),
        ).fetchall()

    def all_enquiries(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM enquiries ORDER BY received_at DESC"
        ).fetchall()

    def touches_for(self, enquiry_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM touches WHERE enquiry_id = ? ORDER BY at", (enquiry_id,)
        ).fetchall()
