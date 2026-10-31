from django.test import TestCase

from apps.security.contracts import ALLOW, DENY, NEEDS_REVIEW
from apps.security.policy import AFTER_APPROVAL, evaluate


class PolicyDeclaredTests(TestCase):
    def setUp(self):
        self.action = "cloudbox.post_payments_payment_id_refund"
        self.spec = {
            "risk": "high",
            "types": {"payment_id": "str", "amount": "number"},
            "required": ["payment_id", "amount"],
            "identifiers": ["payment_id"],
            "amount_param": "amount",
            "auto_max": 50.0,
            "hard_max": 1000.0,
            "prefix": "cloudbox.",
            "rate_limit": 5,
            "idempotency_window": 120,
            "review_vip": True,
        }

    def _ctx(self, verified=None, unmet=None, vip=False):
        return {
            "registry": {self.action: self.spec},
            "verified": verified or {"pay-101"},
            "unmet": unmet or [],
            "facts": {},
            "vip": vip,
        }

    def test_allows_small_refund_with_verified_payment(self):
        ctx = self._ctx(verified={"pay-101"})
        res = evaluate(1, self.action, {"payment_id": "pay-101", "amount": 30.0}, ctx)
        # Risk is high, so it needs review
        self.assertEqual(res.decision, NEEDS_REVIEW)

    def test_low_risk_action_allowed_without_review(self):
        spec = dict(self.spec, risk="low", auto_max=None, hard_max=None)
        ctx = {"registry": {"cloudbox.low": spec}, "verified": {"p-1"}, "unmet": [], "vip": False}
        res = evaluate(1, "cloudbox.low", {"payment_id": "p-1", "amount": 10}, ctx)
        self.assertEqual(res.decision, ALLOW)

    def test_denies_unknown_or_unverified_ownership(self):
        ctx = self._ctx(verified={"pay-101"})
        # Customer names pay-999 which was never returned in reads
        res = evaluate(1, self.action, {"payment_id": "pay-999", "amount": 30.0}, ctx)
        self.assertEqual(res.decision, DENY)
        self.assertEqual(res.rule, "ownership")

    def test_denies_unmet_requirements(self):
        ctx = self._ctx(verified={"pay-101"}, unmet=["payment is successful"])
        res = evaluate(1, self.action, {"payment_id": "pay-101", "amount": 30.0}, ctx)
        self.assertEqual(res.decision, DENY)
        self.assertEqual(res.rule, "requirement_not_met")

    def test_denies_hard_max_exceeded(self):
        ctx = self._ctx(verified={"pay-101"})
        res = evaluate(1, self.action, {"payment_id": "pay-101", "amount": 1500.0}, ctx)
        self.assertEqual(res.decision, DENY)
        self.assertEqual(res.rule, "hard_limit")

    def test_needs_review_when_auto_max_exceeded(self):
        spec = dict(self.spec, risk="low")  # even if risk was low
        ctx = {"registry": {self.action: spec}, "verified": {"pay-101"}, "unmet": [], "vip": False}
        res = evaluate(1, self.action, {"payment_id": "pay-101", "amount": 80.0}, ctx)
        self.assertEqual(res.decision, NEEDS_REVIEW)
        self.assertEqual(res.rule, "auto_limit")

    def test_after_human_approval_skips_review_bands(self):
        ctx = self._ctx(verified={"pay-101"})
        res = evaluate(
            1, self.action, {"payment_id": "pay-101", "amount": 80.0}, ctx, mode=AFTER_APPROVAL
        )
        self.assertEqual(res.decision, ALLOW)

    def test_after_human_approval_still_enforces_hard_limit(self):
        ctx = self._ctx(verified={"pay-101"})
        res = evaluate(
            1, self.action, {"payment_id": "pay-101", "amount": 2000.0}, ctx, mode=AFTER_APPROVAL
        )
        self.assertEqual(res.decision, DENY)
        self.assertEqual(res.rule, "hard_limit")
