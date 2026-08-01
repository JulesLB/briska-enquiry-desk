import json

from _lib import brainlib, guardrail
from _lib.prompts import canned_ack, load_prompt


def process_enquiry(enquiry: str) -> dict[str, object]:
    result = brainlib.run_api(enquiry, load_prompt("system-prompt.md"))
    if "card" not in result:
        return result
    card = result["card"]
    problems = brainlib.validate_card(card) if isinstance(card, dict) else ["no JSON card in brain output"]
    if not isinstance(card, dict) or problems:
        return {
            "card": {
                "language": "en", "bucket": "unclear", "confidence": "low", "stream": "none",
                "urgent": False, "escalate": True,
                "escalation_reasons": ["brain output failed validation"],
                "draft": canned_ack(),
                "log_row": {"summary": enquiry[:80], "next_action": "review by a person"},
            },
            "guardrail": {"blocked": True, "kind": "invalid_card", "problems": problems},
        }
    return _apply_guardrail(card)


def process_followup(followup_type: str, lead: dict[str, object]) -> dict[str, object]:
    request = json.dumps({"followup_due": followup_type, "lead": lead}, ensure_ascii=False, indent=2)
    result = brainlib.run_api(request, load_prompt("followup-prompt.md"))
    if "card" not in result or not isinstance(result["card"], dict):
        return result
    card = result["card"]
    hits = guardrail.scan(card.get("draft") if isinstance(card.get("draft"), str) else None)
    if hits:
        blocked = card.get("draft")
        card = dict(card)
        card["draft"] = None
        card["hold_reason"] = "the safety filter held this draft for a person to review"
        return {
            "card": card,
            "guardrail": {"blocked": True, "kind": "followup_block",
                          "hits": [{"category": h.category, "match": h.match} for h in hits],
                          "original_draft": blocked},
        }
    return {"card": card}


def _apply_guardrail(card: dict[str, object]) -> dict[str, object]:
    draft = card.get("draft") if isinstance(card.get("draft"), str) else None
    escalate = bool(card.get("escalate"))
    hits = guardrail.scan(draft)
    if hits and not escalate:
        blocked_draft = draft
        card = dict(card)
        card["escalate"] = True
        card["escalation_reasons"] = list(card.get("escalation_reasons") or []) + ["guardrail block"]
        card["draft"] = canned_ack()
        return {
            "card": card,
            "guardrail": {"blocked": True, "kind": "draft_block",
                          "hits": [{"category": h.category, "match": h.match} for h in hits],
                          "original_draft": blocked_draft},
        }
    if escalate:
        ack = draft or canned_ack()
        ack_hits = guardrail.scan(ack)
        if ack_hits:
            card = dict(card)
            card["draft"] = canned_ack()
            return {
                "card": card,
                "guardrail": {"blocked": True, "kind": "ack_block",
                              "hits": [{"category": h.category, "match": h.match} for h in ack_hits],
                              "original_draft": ack},
            }
    return {"card": card}
