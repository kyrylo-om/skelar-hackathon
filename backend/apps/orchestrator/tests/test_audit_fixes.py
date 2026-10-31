"""Fixes from the 2026-10-31 agent audit (docs/reviews/dev-agent-audit-2026-10-31.md)."""

import json
import math

from django.test import SimpleTestCase, TestCase, override_settings

from apps.orchestrator import plan as planning
from apps.orchestrator import responder
from apps.orchestrator.gateway import AWAITING, FAILED, ActionOutcome, DevDomainGateway
from apps.orchestrator.manifest import CLOUDBOX
from apps.orchestrator.tests.helpers import make_customer, patch_roles, send
from apps.review.models import ReviewItem
from apps.security.llm import base, complete_json, message_budget
from apps.security.router import ROLES
from apps.support.models import Action

ALLOWED = {a.name: a for a in CLOUDBOX.allowed_actions("activation_issue")}
FACTS = {"payments": [{"id": "p1"}]}


def context_of(user_message: str) -> dict:
    return json.loads(user_message.split("CONTEXT:\n", 1)[1].split("\n\n", 1)[0])


class MalformedPlanTests(SimpleTestCase):
    """A plan the model got wrong anywhere is refused with an error, never with an exception."""

    def check(self, plan):
        return planning.validate_plan(plan, ALLOWED, FACTS)

    def test_a_list_as_the_action_name_is_refused(self):
        assert self.check({"actions": [{"name": [], "params": {}}]})
        assert self.check({"actions": [{"name": {"a": 1}, "params": {}}]})

    def test_params_that_are_not_an_object_are_refused(self):
        assert self.check({"actions": [{"name": "get_payments", "params": []}]})
        assert self.check({"actions": [{"name": "get_payments", "params": "x"}]})

    def test_a_missing_params_field_means_no_params(self):
        assert self.check({"actions": [{"name": "get_payments"}]}) == []

    def test_a_list_as_the_priority_is_refused(self):
        assert self.check({"actions": [], "priority": []})
        assert self.check({"actions": [], "priority": {"x": 1}})

    def test_whatever_else_goes_wrong_is_still_an_error_not_a_crash(self):
        class Exploding(dict):
            def get(self, *args):
                raise RuntimeError("boom")

        assert planning.validate_plan(Exploding(), ALLOWED, FACTS) == [
            "plan could not be inspected"
        ]


SCHEMA = ROLES["triage"]["schema"]


class SchemaRangeTests(SimpleTestCase):
    def valid(self, **extra):
        return base.validate(
            {"intent": "refund", "sentiment": "neutral", "priority": "normal", **extra}, SCHEMA
        )

    def test_confidence_must_be_between_zero_and_one(self):
        assert self.valid(confidence=0) and self.valid(confidence=0.6) and self.valid(confidence=1)
        for bad in (8, -0.1, 1.0001):
            assert not self.valid(confidence=bad), bad

    def test_nan_and_infinity_are_not_numbers(self):
        for bad in (math.nan, math.inf, -math.inf):
            assert not self.valid(confidence=bad), bad

    def test_the_actor_and_critic_schemas_share_the_range(self):
        actor = ROLES["actor"]["schema"]
        assert not base.validate({"actions": [], "confidence": 8}, actor)
        assert base.validate({"actions": [], "confidence": 0.9}, actor)


class DeadlineTests(SimpleTestCase):
    def test_a_message_that_used_up_its_time_gets_the_safe_default(self):
        schema = ROLES["guard"]["schema"]
        with override_settings(LLM_TOTAL_DEADLINE_SEC=0), message_budget():
            result = complete_json("s", "u", schema, "guard", {"attack": True})
        assert result == {"attack": True, "_fallback": True}

    def test_each_call_is_limited_by_the_time_that_is_left(self):
        with override_settings(LLM_TIMEOUT=20, LLM_TOTAL_DEADLINE_SEC=30), message_budget():
            assert base._call_timeout() <= 20
        with override_settings(LLM_TIMEOUT=20, LLM_TOTAL_DEADLINE_SEC=5), message_budget():
            assert 1.0 <= base._call_timeout() <= 5
        with override_settings(LLM_TIMEOUT=20):
            assert base._call_timeout() == 20  # no message budget: just the per-call timeout


class ClaimTests(SimpleTestCase):
    BACKING = "Натисніть «Підтвердити» для вимкнення продовження."

    def test_a_refund_is_never_reported_as_done(self):
        for text in (
            "Гроші вже повернуто на ваш банківський рахунок.",
            "Ми повернули вам кошти.",
            "Your money was refunded.",
        ):
            assert not responder.reply_is_safe(self.BACKING, text), text

    def test_a_waiting_action_is_not_reported_as_finished(self):
        waiting = [ActionOutcome("cancel_auto_renewal", AWAITING)]
        assert not responder.reply_is_safe(self.BACKING, "Автопродовження вимкнено.", waiting)
        assert responder.reply_is_safe(
            self.BACKING, "Натисніть кнопку «Підтвердити» нижче.", waiting
        )

    def test_a_failure_is_not_reported_as_success(self):
        failed = [ActionOutcome("sync_subscription", FAILED, error="x")]
        assert not responder.reply_is_safe("Не вдалося.", "Тариф успішно активовано.", failed)
        assert responder.reply_is_safe("Не вдалося.", "Не вдалося завершити дію.", failed)


class HandoffTests(TestCase):
    def test_a_refund_request_goes_to_a_person_without_asking_the_actor(self):
        user, _ = make_customer()
        with patch_roles(actor="the actor must not be asked"):
            chat = send(user, "Поверніть 99 грн")

        assert chat.reviews.filter(status=ReviewItem.Status.PENDING).exists()

    def test_an_explicit_request_for_a_person_survives_a_total_model_outage(self):
        user, _ = make_customer()
        with patch_roles(triage="garbage", actor="garbage", critic="garbage", responder="garbage"):
            chat = send(user, "Хочу поговорити з людиною")

        assert chat.reviews.filter(status=ReviewItem.Status.PENDING).exists()
        assert "спеціаліст" in chat.messages.filter(role="ai").last().text

    def test_handing_off_rejects_what_the_ai_had_proposed(self):
        user, _ = make_customer()
        send(user, "Скасуйте підписку, не хочу автопродовження")
        assert Action.objects.get(requesting_user=user).status == "awaiting_confirmation"

        rejected = DevDomainGateway(user).hand_off()

        assert rejected == 1
        assert Action.objects.get(requesting_user=user).status == "rejected"

    def test_the_actor_is_told_about_a_confirmation_that_is_still_waiting(self):
        user, _ = make_customer()
        send(user, "Скасуйте підписку, не хочу автопродовження")
        seen = {}

        def ask(user_message):
            seen["context"] = context_of(user_message)
            return {"actions": [], "needs_clarification": "Натисніть кнопку «Підтвердити»."}

        triage = {"intent": "cancel_renewal", "sentiment": "neutral", "priority": "normal"}
        with patch_roles(triage=triage, actor=ask):
            send(user, "так, підтверджую")

        assert seen["context"]["pending_action"]["kind"] == "cancel_auto_renewal"
        assert (
            "id" not in seen["context"]["pending_action"]
        )  # the model never gets the means to confirm
