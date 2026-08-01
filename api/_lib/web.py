import json

from _lib import gate

MAX_BODY_BYTES = 32_000


def read_json(request) -> dict[str, object] | None:
    length = int(request.headers.get("Content-Length", "0"))
    if length <= 0 or length > MAX_BODY_BYTES:
        return None
    try:
        payload = json.loads(request.rfile.read(length).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def send_json(request, status: int, payload: dict[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request.send_response(status)
    request.send_header("Content-Type", "application/json; charset=utf-8")
    request.send_header("Cache-Control", "no-store")
    request.send_header("Content-Length", str(len(body)))
    request.end_headers()
    request.wfile.write(body)


def gatekeeper(request) -> str | None:
    if not gate.check_key(request.headers.get("x-demo-key")):
        return "This demo needs an access link. Ask the person who shared it for the current one."
    allowed, why = gate.allow(gate.client_ip(request.headers))
    if not allowed:
        return why
    return None
