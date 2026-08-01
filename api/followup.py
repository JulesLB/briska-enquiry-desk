import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.pipeline import process_followup
from _lib.web import gatekeeper, read_json, send_json

FOLLOWUP_TYPES = {"chase_1", "chase_2", "final_chase", "booking_reminder", "no_show_rebook", "nurture"}
LEAD_FIELDS = (
    "original_enquiry", "language", "bucket", "stream", "escalate", "escalation_reasons",
    "status", "booked_for", "touches", "last_inbound_at",
)
MAX_TOUCHES = 12


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        refusal = gatekeeper(self)
        if refusal:
            send_json(self, 429, {"error": refusal})
            return
        payload = read_json(self)
        if payload is None:
            send_json(self, 400, {"error": "Bad request body."})
            return
        followup_type = str(payload.get("type", ""))
        lead = payload.get("lead")
        if followup_type not in FOLLOWUP_TYPES or not isinstance(lead, dict):
            send_json(self, 400, {"error": "Need a follow-up type and the lead record."})
            return
        clean = {k: lead.get(k) for k in LEAD_FIELDS}
        touches = clean.get("touches")
        if isinstance(touches, list):
            clean["touches"] = touches[-MAX_TOUCHES:]
        else:
            clean["touches"] = []
        result = process_followup(followup_type, clean)
        result["followup_type"] = followup_type
        send_json(self, 200, result)

    def log_message(self, format: str, *args: object) -> None:
        pass
