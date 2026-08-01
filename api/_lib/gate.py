import hmac
import os
import threading
import time

MAX_ENQUIRY_CHARS = 2000
PER_MINUTE = 6
PER_HOUR = 30
GLOBAL_PER_HOUR = 120

_lock = threading.Lock()
_by_ip: dict[str, list[float]] = {}
_global: list[float] = []


def check_key(supplied: str | None) -> bool:
    expected = os.environ.get("DEMO_KEY", "")
    if not expected:
        return True
    return hmac.compare_digest(expected, supplied or "")


def _prune(stamps: list[float], now: float, window: float) -> list[float]:
    return [s for s in stamps if now - s < window]


def allow(ip: str) -> tuple[bool, str]:
    now = time.time()
    with _lock:
        mine = _prune(_by_ip.get(ip, []), now, 3600)
        recent = [s for s in mine if now - s < 60]
        everyone = _prune(_global, now, 3600)
        if len(recent) >= PER_MINUTE:
            return False, "That is a lot of enquiries in one minute. Give it a moment and try again."
        if len(mine) >= PER_HOUR:
            return False, "This demo caps how many enquiries one visitor can run per hour. Come back a little later."
        if len(everyone) >= GLOBAL_PER_HOUR:
            return False, "The demo is busy right now. Try again in a few minutes."
        mine.append(now)
        everyone.append(now)
        _by_ip[ip] = mine
        _global[:] = everyone
    return True, ""


def client_ip(headers) -> str:
    forwarded = headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return headers.get("x-real-ip", "unknown")
