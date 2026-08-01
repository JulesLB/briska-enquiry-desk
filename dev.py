import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "api"))

if "--mock" in sys.argv:
    os.environ["DEMO_MOCK"] = "1"

from _lib.gate import MAX_ENQUIRY_CHARS
from _lib.pipeline import process_enquiry, process_followup

PORT = int(os.environ.get("DEMO_PORT", "8765"))

PAGES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/dashboard": "dashboard.html",
    "/report": "report.html",
    "/about": "about.html",
}
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


class DevHandler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        name = PAGES.get(self.path.split("?")[0])
        target = HERE / name if name else HERE / self.path.split("?")[0].lstrip("/")
        target = target.resolve()
        if not str(target).startswith(str(HERE)) or not target.is_file():
            self.send_response(404)
            self.end_headers()
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, object] | None:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def do_POST(self) -> None:
        payload = self._body()
        if payload is None:
            self._json(400, {"error": "Bad request body."})
            return
        if self.path == "/api/enquiry":
            enquiry = str(payload.get("enquiry", "")).strip()
            if not enquiry:
                self._json(400, {"error": "Type an enquiry first."})
                return
            if len(enquiry) > MAX_ENQUIRY_CHARS:
                self._json(400, {"error": f"Keep the enquiry under {MAX_ENQUIRY_CHARS} characters for the demo."})
                return
            self._json(200, process_enquiry(enquiry))
            return
        if self.path == "/api/followup":
            followup_type = str(payload.get("type", ""))
            lead = payload.get("lead")
            if not followup_type or not isinstance(lead, dict):
                self._json(400, {"error": "Need a follow-up type and the lead record."})
                return
            result = process_followup(followup_type, lead)
            result["followup_type"] = followup_type
            self._json(200, result)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        sys.stdout.write("  %s %s\n" % (self.command, self.path))
        sys.stdout.flush()


def main() -> None:
    mode = "MOCK brain (no API calls)" if os.environ.get("DEMO_MOCK") == "1" else (
        "LIVE brain via ANTHROPIC_API_KEY" if os.environ.get("ANTHROPIC_API_KEY") else
        "NO brain: set DEMO_MOCK=1 or ANTHROPIC_API_KEY"
    )
    print(f"\nBriska demo dev server on http://127.0.0.1:{PORT}  [{mode}]")
    print("Pages: /  /dashboard  /report  /about   Ctrl+C to stop.\n")
    ThreadingHTTPServer(("127.0.0.1", PORT), DevHandler).serve_forever()


if __name__ == "__main__":
    main()
