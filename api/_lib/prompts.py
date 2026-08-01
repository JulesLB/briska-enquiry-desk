import re
from datetime import date
from functools import lru_cache
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = WEB_ROOT / "prompts"

FIRM_NAME = "[Firm]"
FIRM_PHONE = "[phone]"

PLACEHOLDERS: dict[str, str] = {
    "{{FIRM_NAME}}": FIRM_NAME,
    "{{FIRM_PHONE}}": FIRM_PHONE,
    "{{BOOKING_LINK}}": "[booking link]",
    "{{KNOWN_CLIENTS}}": "(none)",
    "{{DECLINED_STREAMS}}": "(none declared)",
    "{{REFERRAL_POLICY}}": "do not refer out",
    "{{FEE_POLICY}}": "no quotes in writing; the exact quote comes once the right visa is confirmed",
    "{{LANGUAGE_POLICY}}": "reply in the enquiry's language",
}

ACK_TEMPLATE = (
    "Thank you for your enquiry. It has reached {firm_name} and a member of the team is "
    "looking at it now. We will come back to you shortly.\n\n"
    "If your situation is time-sensitive, please call us on {firm_phone}."
)


@lru_cache(maxsize=2)
def load_prompt(name: str) -> str:
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    match = re.search(r"---PROMPT-START---\n(.*?)\n---PROMPT-END---", text, re.DOTALL)
    if match is None:
        raise RuntimeError(f"Prompt markers not found in {name}")
    prompt = match.group(1)
    for placeholder, value in PLACEHOLDERS.items():
        prompt = prompt.replace(placeholder, value)
    return prompt.replace("{{TODAY}}", date.today().isoformat())


def canned_ack() -> str:
    return ACK_TEMPLATE.format(firm_name=FIRM_NAME, firm_phone=FIRM_PHONE)
