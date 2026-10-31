import hashlib
import hmac
import time

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.orchestrator.mcp_gateway import McpGateway
from apps.review.models import Chat

SECRET = "test-widget-secret"


def token(tenant="cloudbox", customer="c-101", ttl=600, secret=SECRET):
    payload = f"{tenant}.{customer}.{int(time.time()) + ttl}"
    return f"{payload}.{hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()}"


def bearer(value):
    return {"HTTP_AUTHORIZATION": f"Bearer {value}"}


def events(response):
    """The streamed body as a list of (event, data) pairs."""
    body = b"".join(response.streaming_content).decode()
    pairs = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        pairs.append((lines["event"], lines["data"]))
    return pairs


@override_settings(WIDGET_SECRETS={"cloudbox": SECRET})
class WidgetApiTests(TestCase):
    def test_chat_needs_a_valid_token(self):
        url = reverse("widget-chat")
        assert self.client.get(url).status_code == 401
        for bad in (
            "garbage",
            token(secret="other"),
            token(ttl=-1),
            token(tenant="unknown"),
            token(customer="c-101:x"),
        ):
            assert self.client.get(url, **bearer(bad)).status_code == 401, bad

    def test_session_login_is_not_enough(self):
        from django.contrib.auth import get_user_model

        self.client.force_login(get_user_model().objects.create_user("cust"))
        assert self.client.get(reverse("widget-chat")).status_code == 401

    def test_token_maps_to_one_chat_per_customer(self):
        url = reverse("widget-chat")
        first = self.client.get(url, **bearer(token())).json()
        again = self.client.get(url, **bearer(token())).json()
        other = self.client.get(url, **bearer(token(customer="c-102"))).json()
        assert first["id"] == again["id"] != other["id"]
        assert first["messages"] == []

    def test_message_streams_the_reply(self):
        response = self.client.post(
            reverse("widget-messages"),
            {"text": "Який у мене тариф?"},
            content_type="application/json",
            **bearer(token()),
        )
        assert response.status_code == 200
        assert response["Content-Type"] == "text/event-stream"
        names = [name for name, _ in events(response)]
        assert names[0] == "status" and names[-1] == "done"
        assert "message" in names
        chat = Chat.objects.get(customer__username="widget:cloudbox:c-101")
        roles = list(chat.messages.values_list("role", flat=True))
        assert roles[0] == "customer" and len(roles) >= 2

    def test_invalid_message_is_rejected_before_streaming(self):
        response = self.client.post(
            reverse("widget-messages"),
            {"text": ""},
            content_type="application/json",
            **bearer(token()),
        )
        assert response.status_code == 400

    @override_settings(EXECUTION_TENANT="cloudbox", EXECUTION_CUSTOMERS={"paid_plus": "c-101"})
    def test_gateway_acts_as_the_token_customer(self):
        self.client.get(reverse("widget-chat"), **bearer(token(tenant="cloudbox", customer="c-7")))
        user = Chat.objects.get().customer
        gateway = McpGateway(user, client=object())
        assert (gateway.tenant, gateway.customer) == ("cloudbox", "c-7")


@override_settings(
    WIDGET_SECRETS={"cloudbox": SECRET},
    ORCHESTRATOR_GATEWAY="mcp",
    EXECUTION_TENANT="cloudbox",
    EXECUTION_SECRET="test-secret",
)
class WidgetConfirmTests(TestCase):
    def setUp(self):
        from unittest import mock

        from apps.orchestrator.tests.test_mcp_gateway import FakeExecutionServer

        self.server = FakeExecutionServer()
        patcher = mock.patch(
            "apps.orchestrator.mcp_gateway.ExecutionClient", return_value=self.server
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, text, customer="c-101"):
        response = self.client.post(
            reverse("widget-messages"),
            {"text": text},
            content_type="application/json",
            **bearer(token(customer=customer)),
        )
        events(response)  # run the stream to the end

    def test_cancellation_runs_only_on_the_customers_button(self):
        self.send("Скасуйте підписку, не хочу автопродовження")
        assert self.server.subscription["auto_renew"] is True
        chat = self.client.get(reverse("widget-chat"), **bearer(token())).json()
        pending = chat["pendingConfirmation"]
        assert pending["kind"] == "cancel_auto_renewal"
        url = reverse("widget-confirm", args=[pending["id"]])

        assert self.client.post(url, **bearer(token(customer="c-102"))).status_code == 404
        assert self.client.post(url).status_code == 401
        assert self.client.post(url, **bearer(token())).status_code == 200
        assert self.server.subscription["auto_renew"] is False
        assert self.client.post(url, **bearer(token())).status_code == 409
        assert len(self.server.executed) == 1

        chat = self.client.get(reverse("widget-chat"), **bearer(token())).json()
        assert chat["pendingConfirmation"] is None
        assert chat["messages"][-1]["role"] == "system"
