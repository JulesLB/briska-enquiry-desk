import unittest

from guardrail import scan


def categories(draft: str) -> set[str]:
    return {hit.category for hit in scan(draft)}


class CleanDrafts(unittest.TestCase):
    def test_hedged_route_language(self) -> None:
        draft = (
            "Thanks for reaching out. Based on what you describe, you may have a route "
            "through QMAS; the consultation confirms whether it fits. Could you share your "
            "age, highest degree, and years of full-time experience?"
        )
        self.assertEqual(categories(draft), set())

    def test_whether_you_qualify(self) -> None:
        self.assertEqual(categories("The consultation will confirm whether you qualify."), set())

    def test_if_you_qualify(self) -> None:
        self.assertEqual(categories("If you qualify, the next step is a short consultation."), set())

    def test_may_qualify(self) -> None:
        self.assertEqual(categories("You may qualify for TTPS Category B."), set())

    def test_might_be_eligible(self) -> None:
        self.assertEqual(categories("You might be eligible depending on the points test."), set())

    def test_recommend_booking(self) -> None:
        self.assertEqual(categories("We recommend booking a consultation this week."), set())

    def test_should_book_call(self) -> None:
        self.assertEqual(categories("You should book a call so a consultant can confirm the route."), set())

    def test_gate_questions_only(self) -> None:
        draft = (
            "To point you in the right direction: which university did you graduate from, "
            "in what year, and how many years of full-time work since?"
        )
        self.assertEqual(categories(draft), set())

    def test_chinese_hedged(self) -> None:
        self.assertEqual(categories("您是否符合資格,需要在諮詢中確認。"), set())

    def test_chinese_recommend_consultation(self) -> None:
        self.assertEqual(categories("我們建議預約一次諮詢,由顧問確認方向。"), set())

    def test_booking_link_no_currency(self) -> None:
        self.assertEqual(categories("You can pick a time here: https://cal.com/firm/15min?ref=42"), set())

    def test_phone_number(self) -> None:
        self.assertEqual(categories("Call us on +852 2234 5678 and quote reference 20260726."), set())

    def test_none_draft(self) -> None:
        self.assertEqual(scan(None), [])

    def test_empty_draft(self) -> None:
        self.assertEqual(scan(""), [])


class VerdictBreaches(unittest.TestCase):
    def test_you_qualify(self) -> None:
        self.assertIn("verdict", categories("Based on what you describe, you qualify for QMAS."))

    def test_sentence_boundary_kills_hedge(self) -> None:
        self.assertIn("verdict", categories("We can check the details later. You qualify for QMAS."))

    def test_you_are_eligible(self) -> None:
        self.assertIn("verdict", categories("You are eligible for the Top Talent Pass."))

    def test_you_will_qualify(self) -> None:
        self.assertIn("verdict", categories("With that degree you will qualify."))

    def test_negative_verdict(self) -> None:
        self.assertIn("verdict", categories("Unfortunately you do not qualify for QMAS."))

    def test_not_eligible(self) -> None:
        self.assertIn("verdict", categories("You are not eligible under GEP."))

    def test_meets_requirements(self) -> None:
        self.assertIn("verdict", categories("You meet the requirements for Category B."))

    def test_application_will_be_approved(self) -> None:
        self.assertIn("verdict", categories("Your application will be approved within weeks."))

    def test_guaranteed_approval(self) -> None:
        self.assertIn("verdict", categories("Approval is guaranteed for profiles like yours."))

    def test_hundred_percent(self) -> None:
        self.assertIn("verdict", categories("We have a 100% success rate with QMAS."))

    def test_chinese_verdict(self) -> None:
        self.assertIn("verdict", categories("你符合資格申請優才計劃。"))

    def test_chinese_negative_verdict(self) -> None:
        self.assertIn("verdict", categories("你不符合資格。"))

    def test_chinese_guarantee(self) -> None:
        self.assertIn("verdict", categories("我們保證獲批。"))

    def test_chinese_certainty(self) -> None:
        self.assertIn("verdict", categories("你一定可以拿到簽證。"))


class FeeBreaches(unittest.TestCase):
    def test_hkd_amount(self) -> None:
        self.assertIn("fee", categories("Our fee is HKD 25,000 for QMAS applications."))

    def test_hk_dollar_sign(self) -> None:
        self.assertIn("fee", categories("The government charges HK$600 for the visa label."))

    def test_bare_dollar(self) -> None:
        self.assertIn("fee", categories("Fees start at $2,000 depending on the case."))

    def test_our_fees_start(self) -> None:
        self.assertIn("fee", categories("Our fees start from a modest base depending on complexity."))

    def test_chinese_amount(self) -> None:
        self.assertIn("fee", categories("費用是20,000港幣。"))

    def test_chinese_fee_phrase(self) -> None:
        self.assertIn("fee", categories("我們的收費是視乎個案而定。"))


class AdviceBreaches(unittest.TestCase):
    def test_should_apply(self) -> None:
        self.assertIn("advice", categories("You should apply for QMAS before the end of the year."))

    def test_advise_submit(self) -> None:
        self.assertIn("advice", categories("We advise you to submit your application immediately."))

    def test_recommend_applying(self) -> None:
        self.assertIn("advice", categories("I recommend applying under Category B right away."))

    def test_need_to_leave(self) -> None:
        self.assertIn("advice", categories("You need to leave Hong Kong before the visa expires."))

    def test_chinese_advice(self) -> None:
        self.assertIn("advice", categories("建議你盡快申請延長逗留。"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
