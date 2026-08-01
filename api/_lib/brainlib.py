import json
import os
import re
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_TIMEOUT_SECONDS = 60
MAX_TOKENS = 1200

BUCKETS = {"qualified", "unclear", "no_fit", "existing_client", "not_an_enquiry"}
STREAMS = {"ttps_a", "ttps_bc", "qmas", "gep", "dependant", "other", "none"}
CONFIDENCES = {"high", "medium", "low"}
LANGUAGES = {"en", "zh-hans", "zh-hant"}


def strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*\n", "", stripped)
        stripped = re.sub(r"\n```\s*$", "", stripped)
    return stripped.strip()


def first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_card(result_text: str) -> dict[str, object] | None:
    fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", result_text, re.DOTALL)
    candidates = [strip_fences(result_text)]
    if fenced:
        candidates.append(fenced.group(1))
    obj = first_json_object(result_text)
    if obj:
        candidates.append(obj)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def validate_card(card: dict[str, object]) -> list[str]:
    problems: list[str] = []
    if str(card.get("bucket")) not in BUCKETS:
        problems.append(f"bad bucket: {card.get('bucket')!r}")
    if str(card.get("confidence")) not in CONFIDENCES:
        problems.append(f"bad confidence: {card.get('confidence')!r}")
    if str(card.get("stream")) not in STREAMS:
        problems.append(f"bad stream: {card.get('stream')!r}")
    if str(card.get("language")) not in LANGUAGES:
        problems.append(f"bad language: {card.get('language')!r}")
    if not isinstance(card.get("escalate"), bool):
        problems.append("escalate is not a bool")
    if not isinstance(card.get("urgent"), bool):
        problems.append("urgent is not a bool")
    draft = card.get("draft")
    if draft is not None and not isinstance(draft, str):
        problems.append("draft is neither string nor null")
    if not isinstance(card.get("log_row"), dict):
        problems.append("log_row missing")
    return problems


def run_api(user_message: str, system_prompt: str) -> dict[str, object]:
    if os.environ.get("DEMO_MOCK") == "1":
        return _mock(user_message, system_prompt)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "The demo backend is missing its API key. Tell the person who sent you this link."}
    model = os.environ.get("DEMO_MODEL", "claude-haiku-4-5")
    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        if exc.code == 429:
            return {"error": "The assistant is at capacity right now. Try again in a minute."}
        return {"error": f"The assistant hit an upstream error ({exc.code}). {detail}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"error": f"The assistant could not be reached: {exc}"}
    blocks = body.get("content", [])
    result_text = "".join(str(b.get("text", "")) for b in blocks if b.get("type") == "text")
    card = parse_card(result_text)
    if card is None:
        return {"raw": result_text.strip()}
    return {"card": card}


def _mock(user_message: str, system_prompt: str) -> dict[str, object]:
    text = user_message.lower()
    if "followup_due" in user_message and '"lead"' in user_message:
        return {"card": {
            "draft": "Hi, just checking back on your enquiry from earlier this week. If you can share your degree, years of experience and current salary, we can tell you which route looks realistic before you commit to anything. Happy to jump on a quick call if that is easier.",
            "hold_reason": None,
            "log_row": {"summary": "follow-up drafted", "next_action": "await reply"},
        }}
    if "overstay" in text or "expired" in text:
        return {"card": {
            "language": "en", "bucket": "qualified", "confidence": "high", "stream": "other",
            "urgent": True, "escalate": True, "escalation_reasons": ["overstay"],
            "draft": "Thank you for reaching out — your message has been passed straight to one of our consultants because timing matters here. Please call us today on [phone] so we can understand where things stand.",
            "log_row": {"summary": "possible overstay, needs a consultant today", "next_action": "consultant calls today"},
        }}
    if "fee" in text or "qualify" in text or "yes or no" in text:
        return {"card": {
            "language": "en", "bucket": "qualified", "confidence": "high", "stream": "qmas",
            "urgent": False, "escalate": False, "escalation_reasons": [],
            "draft": "Thanks for the detail. With a PhD and 10 years in fintech you definitely qualify for QMAS. Our fee is HKD 20,000 and you should apply this month before the quota resets.",
            "log_row": {"summary": "QMAS enquiry, strong profile, fee pressure", "next_action": "review and send"},
        }}
    if re.search(r"[一-鿿]", user_message):
        return {"card": {
            "language": "zh-hant", "bucket": "qualified", "confidence": "medium", "stream": "dependant",
            "urgent": False, "escalate": False, "escalation_reasons": [],
            "draft": "多謝您的查詢。受養人簽證一般適用於配偶及18歲以下子女，父母的個案要視乎具體情況。方便的話，請提供您太太的身份狀況及外母的年齡，我們會盡快回覆您可行的方向。",
            "log_row": {"summary": "dependant visa for mother-in-law, wife is PR", "next_action": "reply sent, await details"},
        }}
    if len(text) < 25:
        return {"card": {
            "language": "en", "bucket": "unclear", "confidence": "medium", "stream": "none",
            "urgent": False, "escalate": False, "escalation_reasons": [],
            "draft": "Thanks for getting in touch. Yes, visas are what we do. To point you in the right direction, could you share what you are looking to do in Hong Kong — work, invest, study or join family — and a line about your background?",
            "log_row": {"summary": "vague enquiry, asked for basics", "next_action": "await details"},
        }}
    return {"card": {
        "language": "en", "bucket": "qualified", "confidence": "medium", "stream": "ttps_bc",
        "urgent": False, "escalate": False, "escalation_reasons": [],
        "draft": "Thanks for the detail — this looks worth a proper conversation. Based on what you have shared, the Top Talent Pass may be the route to check first, and a short call would let us confirm which stream fits. You can pick a time here: [booking link].",
        "log_row": {"summary": "promising profile, booking link sent", "next_action": "await booking"},
    }}
