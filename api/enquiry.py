import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.gate import MAX_ENQUIRY_CHARS
from _lib.pipeline import process_enquiry
from _lib.web import gatekeeper, read_json, send_json


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
        enquiry = str(payload.get("enquiry", "")).strip()
        if not enquiry:
            send_json(self, 400, {"error": "Type an enquiry first."})
            return
        if len(enquiry) > MAX_ENQUIRY_CHARS:
            send_json(self, 400, {"error": f"Keep the enquiry under {MAX_ENQUIRY_CHARS} characters for the demo."})
            return
        send_json(self, 200, process_enquiry(enquiry))

    def log_message(self, format: str, *args: object) -> None:
        pass
