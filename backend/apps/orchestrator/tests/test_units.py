from django.test import SimpleTestCase, TestCase

from apps.orchestrator import plan as planning
from apps.orchestrator import responder
from apps.orchestrator.gateway import AWAITING, DONE, FAILED, ActionOutcome
from apps.orchestrator.manifest import CLOUDBOX, Manifest

FACTS = {
    "subscription": {"id": "s1", "plan": "Free", "period_end": "2026-12-01", "auto_renew": True},
    "payments": [{"id": "p1", "plan": "Plus", "amount": 99.0, "currency": "UAH", "status": "ok"}],
}
ALLOWED = {a.name: a for a in CLOUDBOX.allowed_actions("activation_issue")}


def plan(*actions, clarification=None):
    return {"actions": list(actions), "needs_clarification": clarification}


def sync(payment_id="p1", **extra):
    return {"name": "sync_subscription", "params": {"payment_id": payment_id, **extra}}


class ValidatePlanTests(SimpleTestCase):
    def check(self, plan_):
        return planning.validate_plan(plan_, ALLOWED, FACTS)

    def test_a_well_formed_plan_has_no_problems(self):
        assert self.check(plan(sync())) == []
        assert self.check(plan(clarification="Що саме?")) == []
        assert self.check(plan({"name": "get_payments", "params": {}})) == []

    def test_unknown_or_foreign_actions_are_refused(self):
        assert self.check(plan({"name": "drop_database", "params": {}}))
        assert self.check(
            plan({"name": "cancel_auto_renewal", "params": {}})
        )  # not for this intent

    def test_ids_must_come_from_the_customers_own_facts(self):
        assert self.check(plan(sync("someone-elses-payment")))

    def test_identity_and_unknown_parameters_are_refused(self):
        assert self.check(plan(sync(customer_id=1)))
        assert self.check(plan(sync(note="x")))

    def test_missing_or_non_string_parameters_are_refused(self):
        assert self.check(plan({"name": "sync_subscription", "params": {}}))
        assert self.check(plan({"name": "sync_subscription", "params": {"payment_id": 5}}))

    def test_one_state_changing_action_per_plan(self):
        escalate = {"name": "escalate_to_human", "params": {"reason": "x"}}
        assert self.check(plan(sync(), escalate))

    def test_acting_and_asking_at_once_is_refused(self):
        assert self.check(plan(sync(), clarification="А ще?"))

    def test_malformed_plans_are_refused(self):
        assert self.check("nonsense")
        assert self.check({"actions": "no"})
        assert self.check({"actions": [], "priority": "urgent!!"})
        assert self.check(plan("not an object"))

    def test_strip_identity_keeps_only_the_plan(self):
        raw = {**plan(sync()), "customer_id": 9, "evil": "x"}
        clean = planning.strip_identity(raw)
        assert set(clean) == {"intent", "confidence", "priority", "needs_clarification", "actions"}


class ManifestTests(SimpleTestCase):
    def test_the_bundled_manifest_is_valid(self):
        CLOUDBOX.validate()

    def test_an_action_unknown_to_policy_is_refused(self):
        bad = Manifest(
            "t",
            "T",
            "uk",
            {"fly": CLOUDBOX.actions["get_payments"].__class__("fly", "x")},
            {},
            CLOUDBOX.escalation,
            CLOUDBOX.responses,
        )
        with self.assertRaises(ValueError):
            bad.validate()

    def test_an_intent_with_an_unknown_action_is_refused(self):
        from apps.orchestrator.manifest import IntentSpec

        bad = Manifest(
            "t",
            "T",
            "uk",
            CLOUDBOX.actions,
            {"x": IntentSpec("x", ("nope",))},
            CLOUDBOX.escalation,
            CLOUDBOX.responses,
        )
        with self.assertRaises(ValueError):
            bad.validate()

    def test_missing_templates_are_refused(self):
        bad = Manifest("t", "T", "uk", {}, {}, CLOUDBOX.escalation, {"review": "x"})
        with self.assertRaises(ValueError):
            bad.validate()

    def test_always_human_intents_cannot_act_on_their_own(self):
        for intent in ("legal_threat", "account_deletion", "payment_method_change"):
            assert CLOUDBOX.intents[intent].always_human


class ResponderTests(TestCase):
    def reply(self, outcome, facts=FACTS):
        return responder.action_reply(outcome, facts, CLOUDBOX)

    def test_a_synced_plan_names_the_real_plan_and_date(self):
        outcome = ActionOutcome(
            "sync_subscription", DONE, facts={"plan": "Plus", "period_end": "2026-11-30"}
        )
        assert self.reply(outcome) == "Знайшов ваш платіж. Тариф Plus активовано до 2026-11-30."

    def test_a_failed_action_is_never_reported_as_done(self):
        outcome = ActionOutcome("sync_subscription", FAILED, error="x")
        assert "Не вдалося" in self.reply(outcome)

    def test_a_cancellation_asks_for_the_button(self):
        outcome = ActionOutcome("cancel_auto_renewal", AWAITING)
        assert "Підтвердити" in self.reply(outcome)

    def test_status_reads_come_from_the_facts(self):
        text = self.reply(ActionOutcome("get_subscription", DONE))
        assert "Free" in text and "2026-12-01" in text and "увімкнено" in text

    def test_missing_data_gets_an_honest_answer(self):
        assert "Не бачу" in self.reply(ActionOutcome("get_subscription", DONE), {"payments": []})
        assert "Оплат поки не бачу" in self.reply(
            ActionOutcome("get_payments", DONE), {"payments": []}
        )
