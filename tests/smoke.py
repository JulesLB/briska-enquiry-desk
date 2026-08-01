import os
import sys
import unittest
from pathlib import Path

os.environ["DEMO_MOCK"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from _lib.brainlib import validate_card
from _lib.pipeline import process_enquiry, process_followup
from _lib.prompts import canned_ack


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
