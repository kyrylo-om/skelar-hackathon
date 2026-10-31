from django.test import TestCase, override_settings

from apps.security import policy
from apps.security.contracts import ALLOW, DENY, NEEDS_REVIEW
from apps.security.models import ActionLog

ME = 7
CTX = {
    "orders": {
        "1042": {"customer_id": ME, "status": "processing", "total": 6000},
        "1043": {"customer_id": ME, "status": "shipped", "total": 6000},
        "9999": {"customer_id": 99, "status": "processing", "total": 100},
    },
    "subscriptions": {"s1": {"customer_id": ME}},
}


def refund(amount, order="1042", **ctx):
    return policy.evaluate(ME, "issue_refund", {"order": order, "amount": amount}, {**CTX, **ctx})


class PolicyTests(TestCase):
    def test_unknown_action_is_denied(self):
        result = policy.evaluate(ME, "drop_database", {}, CTX)
        assert (result.decision, result.rule) == (DENY, "unknown_action")

    def test_invalid_params_are_denied(self):
        for params in (
            {"order": "1042"},
            {"order": "1042", "amount": -5},
            {"order": "1042", "amount": True},
        ):
            result = policy.evaluate(ME, "issue_refund", params, CTX)
            assert (result.decision, result.rule) == (DENY, "invalid_params"), params

    def test_someone_elses_order_is_denied(self):
        result = refund(30, order="9999")
        assert (result.decision, result.rule) == (DENY, "ownership")

    def test_missing_order_looks_the_same_as_foreign_order(self):
        assert refund(30, order="nope").rule == "ownership"

    def test_subscription_ownership(self):
        assert (
            policy.evaluate(ME, "pause_subscription", {"subscription": "s1"}, CTX).decision == ALLOW
        )
        other = {"subscriptions": {"s1": {"customer_id": 1}}}
        assert (
            policy.evaluate(ME, "pause_subscription", {"subscription": "s1"}, other).rule
            == "ownership"
        )

    def test_status_read_is_allowed(self):
        result = policy.evaluate(ME, "get_order_status", {"order": "1043"}, CTX)
        assert result.decision == ALLOW

    def test_cancel_only_while_processing(self):
        assert policy.evaluate(ME, "cancel_order", {"order": "1042"}, CTX).decision == ALLOW
        shipped = policy.evaluate(ME, "cancel_order", {"order": "1043"}, CTX)
        assert (shipped.decision, shipped.rule) == (DENY, "status")

    def test_refund_limits(self):
        assert refund(30).decision == ALLOW
        review = refund(300)
        assert (review.decision, review.rule) == (NEEDS_REVIEW, "refund_auto_limit")
        hard = refund(5000)
        assert (hard.decision, hard.rule) == (DENY, "refund_hard_limit")

    def test_refund_cannot_exceed_the_order_total(self):
        ctx = {"orders": {"1042": {"customer_id": ME, "status": "processing", "total": 100}}}
        result = policy.evaluate(ME, "issue_refund", {"order": "1042", "amount": 200}, ctx)
        assert result.rule == "amount_exceeds_order"

    @override_settings(AUTO_REFUND_LIMIT=500)
    def test_limits_come_from_settings(self):
        assert refund(300).decision == ALLOW

    def test_repeated_action_is_denied(self):
        params = {"order": "1042", "amount": 30}
        assert refund(30).decision == ALLOW
        policy.record(ME, "issue_refund", params)
        result = refund(30)
        assert (result.decision, result.rule) == (DENY, "idempotency")

    def test_different_params_are_not_a_repeat(self):
        policy.record(ME, "issue_refund", {"order": "1042", "amount": 30})
        assert refund(40).decision == ALLOW

    @override_settings(RISKY_ACTIONS_PER_HOUR=2)
    def test_rate_limit_on_risky_actions(self):
        for amount in (10, 20):
            policy.record(ME, "issue_refund", {"order": "1042", "amount": amount})
        result = refund(30)
        assert (result.decision, result.rule) == (DENY, "rate_limit")

    @override_settings(RISKY_ACTIONS_PER_HOUR=1)
    def test_rate_limit_ignores_other_customers_and_low_risk(self):
        ActionLog.objects.create(customer_id=1, action="issue_refund", params_hash="x")
        policy.record(ME, "get_order_status", {"order": "1042"})
        assert refund(30).decision == ALLOW

    def test_high_risk_action_needs_review(self):
        result = policy.evaluate(ME, "change_payment_method", {}, CTX)
        assert (result.decision, result.rule) == (NEEDS_REVIEW, "high_risk")

    def test_handing_off_to_a_human_goes_through_review(self):
        result = policy.evaluate(ME, "escalate_to_human", {}, CTX)
        assert (result.decision, result.rule) == (NEEDS_REVIEW, "human_requested")

    def test_vip_needs_review_and_is_configurable(self):
        assert refund(30, vip=True).rule == "vip"
        with override_settings(POLICY_REVIEW_VIP=False):
            assert refund(30, vip=True).decision == ALLOW

    def test_strictest_outcome_wins(self):
        # 300 asks for review, but the repeat inside the window denies it outright.
        policy.record(ME, "issue_refund", {"order": "1042", "amount": 300})
        assert refund(300).decision == DENY

    def test_missing_context_is_safe(self):
        assert policy.evaluate(ME, "cancel_order", {"order": "1042"}).decision == DENY
