"""The pipeline driving an external product through the execution server (ORCHESTRATOR_GATEWAY=mcp).

The execution server is replaced by an in-memory stand-in with the CloudBox mock's behaviour, so
these run offline like the rest of the suite. The real server is covered by execution/tests.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.orchestrator.mcp_gateway import ProductUnavailable
from apps.orchestrator.models import ProductConfirmation
from apps.orchestrator.tests.helpers import agents, last_reply, send
from apps.review import services as review_services
from apps.review.models import Chat, ReviewItem

User = get_user_model()


class FakeExecutionServer:
    """CloudBox customer c-101 behind the execution server: Free, with an unapplied Plus payment."""

    def __init__(self):
        self.subscription = {
            "id": "sub-1",
            "plan": "Free",
            "status": "active",
            "period_end": None,
            "auto_renew": True,
        }
        self.payments = [
            {
                "id": "pay-501",
                "plan": "Plus",
                "amount": 99,
                "status": "successful",
                "applied_at": None,
            }
        ]
        self.proposals = {}
        self.executed = []
        self.tokens = set()
        self.down = False
        self.refuse = None

    def read(self, token, path):
        if self.down:
            raise ProductUnavailable("execution server is not reachable")
        self.tokens.add(token.rsplit(".", 2)[0])
        data = {"/subscription": self.subscription, "/payments": self.payments}[path]
        return {"http_status": 200, "data": data}

    def propose(self, token, method, path, summary, body):
        proposal_id = f"prop-{len(self.proposals) + 1}"
        self.proposals[proposal_id] = (method, path, body)
        return {"proposal_id": proposal_id, "status": "proposed"}

    def execute(self, proposal_id):
        if proposal_id in self.executed:
            raise ProductUnavailable("Proposal is executed")
        self.executed.append(proposal_id)
        if self.refuse:
            body = {"detail": self.refuse}
            return {"status": "failed", "result": {"http_status": 409, "body": body}}
        method, path, body = self.proposals[proposal_id]
        if path == "/subscription/sync":
            payment = next(p for p in self.payments if p["id"] == body["payment_id"])
            payment["applied_at"] = "2026-10-31T12:00:00+00:00"
            self.subscription |= {
                "plan": payment["plan"],
                "period_end": "2026-11-30T12:00:00+00:00",
            }
        elif path == "/subscription/auto-renewal/off":
            self.subscription["auto_renew"] = False
        return {"status": "executed", "result": {"http_status": 200, "body": self.subscription}}


@override_settings(
    ORCHESTRATOR_GATEWAY="mcp",
    EXECUTION_TENANT="cloudbox",
    EXECUTION_SECRET="test-secret",
    EXECUTION_CUSTOMERS={"olena": "c-101"},
)
class McpGatewayTests(TestCase):
    def setUp(self):
        self.server = FakeExecutionServer()
        patcher = mock.patch(
            "apps.orchestrator.mcp_gateway.ExecutionClient", return_value=self.server
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_user("olena", password="synthetic-pass-123")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_activation_runs_through_the_execution_server(self):
        chat = send(self.user, "Оплатив Plus, а тариф досі Free")

        assert self.server.subscription["plan"] == "Plus"
        assert self.server.executed == ["prop-1"]
        assert self.server.proposals["prop-1"][1:] == (
            "/subscription/sync",
            {"payment_id": "pay-501"},
        )
        assert self.server.tokens == {"cloudbox.c-101"}  # identity from settings, not the model
        assert "Plus" in last_reply(chat)
        assert agents(chat)[-1] == "executor"
        assert chat.status == Chat.Status.AI_HANDLING

    def test_a_status_question_only_reads(self):
        chat = send(self.user, "який у мене тариф?")

        assert "Free" in last_reply(chat)
        assert self.server.proposals == {}

    def test_cancellation_waits_for_the_customers_button(self):
        send(self.user, "Скасуйте підписку, не хочу автопродовження")
        assert self.server.proposals and not self.server.executed
        assert self.server.subscription["auto_renew"] is True

        client = self.client_for(self.user)
        pending = client.get("/api/review/my/chat/").json()["pendingConfirmation"]
        assert pending["kind"] == "cancel_auto_renewal"

        confirmed = client.post(f"/api/actions/{pending['id']}/confirm/", {}, format="json")
        assert confirmed.status_code == 200
        assert self.server.subscription["auto_renew"] is False
        assert client.get("/api/review/my/chat/").json()["pendingConfirmation"] is None
        again = client.post(f"/api/actions/{pending['id']}/confirm/", {}, format="json")
        assert again.status_code == 409
        assert len(self.server.executed) == 1

    def test_another_customer_cannot_confirm(self):
        send(self.user, "Скасуйте підписку, не хочу автопродовження")
        pending = ProductConfirmation.objects.get(customer=self.user)
        stranger = User.objects.create_user("stranger", password="synthetic-pass-123")

        response = self.client_for(stranger).post(
            f"/api/actions/{pending.pk}/confirm/", {}, format="json"
        )
        assert response.status_code == 404
        assert self.server.executed == []

    def test_no_confirmation_after_the_chat_went_to_a_human(self):
        send(self.user, "Скасуйте підписку, не хочу автопродовження")
        pending = ProductConfirmation.objects.get(customer=self.user)
        review_services.escalate(review_services.chat_for_customer(self.user))

        response = self.client_for(self.user).post(
            f"/api/actions/{pending.pk}/confirm/", {}, format="json"
        )
        assert response.status_code == 409
        assert self.server.executed == []

    def test_a_hand_off_rejects_waiting_confirmations(self):
        send(self.user, "Скасуйте підписку, не хочу автопродовження")
        send(self.user, "Хочу поговорити з людиною")

        pending = ProductConfirmation.objects.get(customer=self.user)
        assert pending.status == ProductConfirmation.Status.REJECTED
        assert (
            self.client_for(self.user).get("/api/review/my/chat/").json()["pendingConfirmation"]
            is None
        )

    def test_unreachable_product_goes_to_a_human(self):
        self.server.down = True
        chat = send(self.user, "Оплатив Plus, а тариф досі Free")

        assert chat.status == Chat.Status.NEEDS_REVIEW
        assert chat.reviews.filter(status=ReviewItem.Status.PENDING).exists()
        assert self.server.proposals == {}

    def test_an_account_not_connected_to_the_product_goes_to_a_human(self):
        other = User.objects.create_user("unmapped", password="synthetic-pass-123")
        chat = send(other, "Оплатив Plus, а тариф досі Free")

        assert chat.status == Chat.Status.NEEDS_REVIEW
        assert self.server.tokens == set()

    def test_a_product_refusal_is_reported_and_handed_over(self):
        self.server.refuse = "The payment is already applied"
        chat = send(self.user, "Оплатив Plus, а тариф досі Free")

        assert self.server.subscription["plan"] == "Free"
        assert chat.status == Chat.Status.NEEDS_REVIEW
        assert agents(chat)[-2:] == ["executor", "human"]

    def test_an_operator_approval_runs_through_the_execution_server(self):
        operator = User.objects.create_user("op", password="synthetic-pass-123", is_staff=True)
        chat = review_services.chat_for_customer(self.user)
        item = review_services.open_review(
            chat,
            action="sync_subscription",
            params={"payment_id": "pay-501"},
            risk="medium",
            reason="test",
        )

        review_services.decide_review(item.pk, operator, "approved", "ok")

        assert self.server.subscription["plan"] == "Plus"
        assert len(self.server.executed) == 1
