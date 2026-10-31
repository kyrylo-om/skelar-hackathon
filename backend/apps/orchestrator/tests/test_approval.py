from django.test import TestCase
from rest_framework.test import APIClient

from apps.orchestrator.tests.helpers import make_customer, send
from apps.review import ports, services
from apps.review.models import Chat, ReviewItem
from apps.security.models import ActionLog
from apps.subscriptions.models import Payment, Subscription
from apps.support.models import Action


def pending_review(user, action, params):
    chat = services.chat_for_customer(user)
    return services.open_review(chat, action=action, params=params, risk="medium", reason="test")


class ApprovedActionTests(TestCase):
    def setUp(self):
        self.operator, _ = make_customer("op", payment=False, subscription=False)
        self.operator.is_staff = True
        self.operator.save()

    def test_an_approved_sync_runs_after_policy_checks_again(self):
        user, payment = make_customer()
        item = pending_review(user, "sync_subscription", {"payment_id": str(payment.pk)})

        services.decide_review(item.pk, self.operator, "approved", "ok")

        assert Subscription.objects.get(user=user).plan.name == "Plus"
        assert Payment.objects.get(pk=payment.pk).applied_at is not None
        assert ActionLog.objects.filter(customer_id=user.pk, action="sync_subscription").exists()
        assert ReviewItem.objects.get(pk=item.pk).status == ReviewItem.Status.APPROVED

    def test_policy_still_denies_an_approved_action_whose_facts_changed(self):
        user, payment = make_customer(applied=True)  # someone already used this payment
        item = pending_review(user, "sync_subscription", {"payment_id": str(payment.pk)})

        with self.assertRaises(ports.ExecutionError):
            services.decide_review(item.pk, self.operator, "approved", "ok")

        item.refresh_from_db()
        assert item.status == ReviewItem.Status.PENDING  # still waiting, nothing executed
        assert not Action.objects.filter(requesting_user=user).exists()

    def test_an_action_the_product_cannot_do_stays_pending(self):
        user, _ = make_customer()
        item = pending_review(user, "change_payment_method", {})

        with self.assertRaises(ports.ExecutionError):
            services.decide_review(item.pk, self.operator, "approved", "ok")

        item.refresh_from_db()
        assert item.status == ReviewItem.Status.PENDING

    def test_approving_a_handoff_just_closes_it(self):
        user, _ = make_customer()
        item = pending_review(user, "escalate_to_human", {"reason": "x"})

        services.decide_review(item.pk, self.operator, "approved", "")

        item.refresh_from_db()
        assert item.status == ReviewItem.Status.APPROVED

    def test_someone_elses_payment_can_never_be_applied_by_approval(self):
        user, _ = make_customer()
        _, other_payment = make_customer("other")
        item = pending_review(user, "sync_subscription", {"payment_id": str(other_payment.pk)})

        with self.assertRaises(ports.ExecutionError):
            services.decide_review(item.pk, self.operator, "approved", "ok")

        assert Payment.objects.get(pk=other_payment.pk).applied_at is None


class CustomerApiTests(TestCase):
    def test_the_chat_api_runs_the_pipeline_and_exposes_the_confirm_button(self):
        user, _ = make_customer()
        client = APIClient()
        client.force_login(user)

        sent = client.post(
            "/api/review/my/chat/messages/", {"text": "Скасуйте підписку, не хочу"}, format="json"
        )

        assert sent.status_code == 201
        data = sent.json()
        assert set(data) == {"id", "status", "messages", "pendingConfirmation"}
        assert data["pendingConfirmation"]["kind"] == "cancel_auto_renewal"
        assert data["messages"][-1]["role"] == "ai"
        assert "Підтвердити" in data["messages"][-1]["text"]

    def test_the_customer_never_sees_the_trace_or_review_internals(self):
        user, _ = make_customer()
        client = APIClient()
        client.force_login(user)

        data = client.post(
            "/api/review/my/chat/messages/", {"text": "Поверніть 99 грн"}, format="json"
        ).json()

        assert "trace" not in data and "review" not in data
        assert data["status"] == Chat.Status.NEEDS_REVIEW

    def test_the_chat_polls_cheaply_without_running_the_pipeline(self):
        user, _ = make_customer()
        client = APIClient()
        client.force_login(user)
        client.get("/api/review/my/chat/")
        client.get("/api/review/my/chat/")

        assert not Action.objects.exists()
        assert not Chat.objects.get(customer=user).messages.exists()

    def test_one_customer_cannot_see_or_confirm_anothers_cancellation(self):
        victim, _ = make_customer("victim")
        send(victim, "Скасуйте підписку, не хочу")
        attacker, _ = make_customer("attacker")
        client = APIClient()
        client.force_login(attacker)

        assert client.get("/api/review/my/chat/").json()["pendingConfirmation"] is None
        action = Action.objects.get(requesting_user=victim)
        assert (
            client.post(f"/api/actions/{action.pk}/confirm/", {}, format="json").status_code == 404
        )
        assert Subscription.objects.get(user=victim).auto_renew is True
