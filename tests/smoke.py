import os
import sys
import unittest
from pathlib import Path

os.environ["DEMO_MOCK"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from _lib import brainlib
from _lib.brainlib import parse_card, validate_card
from _lib.pipeline import process_enquiry, process_followup
from _lib.prompts import canned_ack

RAW_NEWLINE_CARD = '''```json
{
  "bucket": "qualified", "confidence": "high", "stream": "qmas", "language": "en",
  "urgent": false, "escalate": false, "escalation_reasons": [],
  "draft": "First paragraph.

Second paragraph.",
  "log_row": {"summary": "s", "next_action": "n"}
}
```'''


class PipelineSmoke(unittest.TestCase):
    def test_guardrail_blocks_verdict_and_fee(self) -> None:
        result = process_enquiry("38, PhD, 10 years fintech. Yes or no: do I qualify for QMAS? And your exact fee.")
        guardrail = result.get("guardrail")
        self.assertIsNotNone(guardrail)
        self.assertTrue(guardrail["blocked"])
        self.assertEqual(guardrail["kind"], "draft_block")
        categories = {h["category"] for h in guardrail["hits"]}
        self.assertIn("verdict", categories)
        self.assertIn("fee", categories)
        self.assertTrue(result["card"]["escalate"])
        self.assertEqual(result["card"]["draft"], canned_ack())
        self.assertIn("guardrail block", result["card"]["escalation_reasons"])

    def test_overstay_escalates_without_block(self) -> None:
        result = process_enquiry("My visa expired 3 weeks ago and I'm still in HK, what do I do?")
        self.assertTrue(result["card"]["escalate"])
        self.assertNotIn("guardrail", result)
        self.assertEqual(validate_card(result["card"]), [])

    def test_clean_enquiry_passes_untouched(self) -> None:
        result = process_enquiry("Hello, I run a small design studio in Singapore and I am exploring a move to Hong Kong next year with my family.")
        self.assertFalse(result["card"]["escalate"])
        self.assertNotIn("guardrail", result)
        self.assertEqual(validate_card(result["card"]), [])

    def test_raw_newlines_in_draft_still_parse(self) -> None:
        card = parse_card(RAW_NEWLINE_CARD)
        self.assertIsNotNone(card)
        self.assertEqual(validate_card(card), [])
        self.assertIn("Second paragraph.", card["draft"])

    def test_unparseable_output_falls_to_the_safe_floor(self) -> None:
        original = brainlib.run_api
        brainlib.run_api = lambda message, prompt: {"raw": "I cannot help with that."}
        try:
            result = process_enquiry("Do I qualify for QMAS?")
            followup = process_followup("chase_1", {"original_enquiry": "hi", "touches": []})
        finally:
            brainlib.run_api = original
        self.assertTrue(result["card"]["escalate"])
        self.assertEqual(result["card"]["draft"], canned_ack())
        self.assertEqual(result["guardrail"]["kind"], "unparsed_output")
        self.assertIsNone(followup["card"]["draft"])
        self.assertTrue(followup["card"]["hold_reason"])

    def test_canned_ack_has_no_em_dash(self) -> None:
        self.assertNotIn("—", canned_ack())

    def test_followup_drafts(self) -> None:
        lead = {
            "original_enquiry": "hi do you do visa", "language": "en", "bucket": "unclear",
            "stream": "none", "escalate": False, "escalation_reasons": [],
            "status": "awaiting_reply", "booked_for": None, "touches": [],
            "last_inbound_at": "2026-08-01T10:00",
        }
        result = process_followup("chase_1", lead)
        self.assertTrue(result["card"]["draft"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
