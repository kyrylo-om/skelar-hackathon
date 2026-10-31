"""Required safety behavior missing from the original dev test coverage.

These database integration regressions were added during the 2026-10-31 audit.
They require the normal requirements-dev environment; the offline audit script does
not execute them and must not be reported as a substitute for this suite.
"""

from unittest import mock

from django.test import TestCase
from rest_framework.exceptions import APIException

from apps.orchestrator import pipeline
from apps.orchestrator.facts import load_facts, policy_ctx
from apps.orchestrator.tests.helpers import make_customer, patch_roles, send
from apps.review import services as review_services
from apps.review.models import Chat, ReviewItem
from apps.security import critic
from apps.subscriptions.models import Payment, Subscription
from apps.support import services as support
from apps.support.models import Action


class InstructionRegressionTests(TestCase):
    def test_human_request_reaches_queue_when_triage_is_unavailable(self):
        user, _ = make_customer()
        with patch_roles(triage="invalid json"):
            chat = send(user, "Хочу поговорити з людиною")
        assert chat.status == Chat.Status.NEEDS_REVIEW
        assert chat.reviews.filter(status=ReviewItem.Status.PENDING).exists()

    def test_refund_request_reaches_queue_when_triage_is_unavailable(self):
        user, _ = make_customer()
        with patch_roles(triage="invalid json"):
            chat = send(user, "Поверніть 99 грн")
        assert chat.status == Chat.Status.NEEDS_REVIEW
        assert chat.reviews.filter(status=ReviewItem.Status.PENDING).exists()

    def test_critic_receives_payment_evidence_from_backend(self):
        user, payment = make_customer()
        context = policy_ctx(user, load_facts(user))
        plan = {
            "actions": [
                {"name": "sync_subscription", "params": {"payment_id": str(payment.pk)}}
            ]
        }
        with mock.patch.object(
            critic.router, "route", return_value={"verdict": "approve", "reason": "ok"}
        ) as route:
            critic.review_plan("Оплатив Plus, а тариф досі Free", plan, context)
        assert route.call_args.args[1]["context"].get("payments") == context["payments"]

    def test_customer_cannot_confirm_pending_ai_action_after_handoff(self):
        user, _ = make_customer()
        send(user, "Скасуйте підписку, не хочу автопродовження")
        pending = pipeline.pending_confirmation(user)
        assert pending is not None
        chat = send(user, "Хочу поговорити з людиною")
        assert chat.status == Chat.Status.NEEDS_REVIEW

        with self.assertRaises(APIException):
            support.confirm_cancellation(user, pending["id"])

        assert Subscription.objects.get(user=user).auto_renew is True
        assert Action.objects.get(pk=pending["id"]).status != "succeeded"

    def test_actor_result_cannot_mutate_after_handoff_during_model_call(self):
        user, payment = make_customer()

        def handoff_while_actor_runs(_payload):
            chat = review_services.chat_for_customer(user)
            review_services.open_review(
                chat,
                action="escalate_to_human",
                params={"reason": "Customer requested a human during the model call"},
                risk="high",
                reason="Concurrent handoff",
            )
            return {
                "actions": [
                    {"name": "sync_subscription", "params": {"payment_id": str(payment.pk)}}
                ],
                "needs_clarification": None,
            }

        with patch_roles(actor=handoff_while_actor_runs):
            chat = send(user, "Оплатив Plus, а тариф досі Free")

        assert chat.status == Chat.Status.NEEDS_REVIEW
        assert Payment.objects.get(pk=payment.pk).applied_at is None
        assert Subscription.objects.get(user=user).plan.name == "Free"
