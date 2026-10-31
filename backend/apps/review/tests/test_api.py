from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.review import ports, services
from apps.review.models import AuditLog, Chat, ReviewItem
from apps.review.permissions import OPERATOR_GROUP

PASSWORD = "test-pass-123"


class SupportApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        group = Group.objects.create(name=OPERATOR_GROUP)
        cls.operator = user_model.objects.create_user("op", password=PASSWORD)
        cls.operator.groups.add(group)
        cls.customer = user_model.objects.create_user("cust", password=PASSWORD)

    def setUp(self):
        cache.clear()
        self.chat = Chat.objects.create(customer_name="Олена", subject="Повернення")
        self.review = services.open_review(
            self.chat, action="refund", params={"amount": 240}, risk="high", reason="ліміт"
        )

    def login(self, user=None):
        self.client.force_login(user or self.operator)

    # auth

    def test_login_requires_operator(self):
        response = self.client.post(
            reverse("login"),
            {"username": "cust", "password": PASSWORD},
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_login_rejects_bad_password(self):
        response = self.client.post(
            reverse("login"),
            {"username": "op", "password": "nope"},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_login_and_me(self):
        response = self.client.post(
            reverse("login"),
            {"username": "op", "password": PASSWORD},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert self.client.get(reverse("me")).json() == {"username": "op", "isOperator": True}

    def test_login_is_throttled(self):
        for _ in range(10):
            self.client.post(
                reverse("login"),
                {"username": "op", "password": "x"},
                content_type="application/json",
            )
        response = self.client.post(
            reverse("login"), {"username": "op", "password": "x"}, content_type="application/json"
        )
        assert response.status_code == 429

    # access control

    def test_anonymous_and_customers_cannot_read_chats(self):
        assert self.client.get(reverse("chat-list")).status_code == 403
        self.login(self.customer)
        assert self.client.get(reverse("chat-list")).status_code == 403
        assert self.client.get(reverse("chat-detail", args=[self.chat.pk])).status_code == 403

    # reading

    def test_list_filters_and_search(self):
        Chat.objects.create(customer_name="Іван", subject="Пауза", status=Chat.Status.RESOLVED)
        self.login()
        url = reverse("chat-list")
        assert len(self.client.get(url).json()) == 2
        assert len(self.client.get(url, {"status": "resolved"}).json()) == 1
        assert self.client.get(url, {"q": "олен"}).json()[0]["customer"] == "Олена"

    def test_detail_includes_pending_review(self):
        self.login()
        data = self.client.get(reverse("chat-detail", args=[self.chat.pk])).json()
        assert data["review"]["status"] == "pending"
        assert data["review"]["id"] == self.review.pk

    # replying

    def test_reply_is_saved_and_audited(self):
        self.login()
        response = self.client.post(
            reverse("chat-reply", args=[self.chat.pk]),
            {"text": "Вже дивлюсь"},
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response.json()["messages"][-1]["role"] == "operator"
        assert AuditLog.objects.filter(event="operator_reply").exists()

    def test_empty_reply_is_rejected(self):
        self.login()
        response = self.client.post(
            reverse("chat-reply", args=[self.chat.pk]),
            {"text": "  "},
            content_type="application/json",
        )
        assert response.status_code == 400

    # review decisions

    def decide(self, decision):
        return self.client.post(
            reverse("review-decision", args=[self.review.pk]),
            {"decision": decision},
            content_type="application/json",
        )

    def test_approve_executes_and_resolves(self):
        self.login()
        with mock.patch.object(ports, "execute") as execute:
            response = self.decide("approved")
        assert response.status_code == 200
        execute.assert_called_once_with("refund", {"amount": 240})
        self.chat.refresh_from_db()
        self.review.refresh_from_db()
        assert self.chat.status == Chat.Status.RESOLVED
        assert self.review.status == ReviewItem.Status.APPROVED
        assert self.review.decided_by == self.operator
        assert AuditLog.objects.filter(event="review_approved").exists()

    def test_reject_does_not_execute(self):
        self.login()
        with mock.patch.object(ports, "execute") as execute:
            response = self.decide("rejected")
        assert response.status_code == 200
        execute.assert_not_called()
        self.review.refresh_from_db()
        assert self.review.status == ReviewItem.Status.REJECTED

    def test_second_decision_conflicts(self):
        self.login()
        self.decide("rejected")
        with mock.patch.object(ports, "execute") as execute:
            response = self.decide("approved")
        assert response.status_code == 409
        execute.assert_not_called()

    def test_failed_execution_keeps_review_pending(self):
        self.login()
        with mock.patch.object(ports, "execute", side_effect=ports.ExecutionError("API down")):
            response = self.decide("approved")
        assert response.status_code == 502
        self.review.refresh_from_db()
        self.chat.refresh_from_db()
        assert self.review.status == ReviewItem.Status.PENDING
        assert self.chat.status == Chat.Status.NEEDS_REVIEW
        assert not AuditLog.objects.filter(event="review_approved").exists()

    def test_invalid_decision_is_rejected(self):
        self.login()
        assert self.decide("maybe").status_code == 400


class CustomerChatTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.customer = user_model.objects.create_user("cust", password=PASSWORD)
        cls.other = user_model.objects.create_user("other", password=PASSWORD)
        cls.operator = user_model.objects.create_user("op", password=PASSWORD, is_staff=True)

    def setUp(self):
        cache.clear()

    def post_json(self, name, data):
        return self.client.post(reverse(name), data, content_type="application/json")

    def test_customer_login_needs_customer_role(self):
        ok = self.post_json("login", {"username": "cust", "password": PASSWORD, "role": "customer"})
        assert ok.status_code == 200
        assert ok.json() == {"username": "cust", "isOperator": False}
        self.client.logout()
        wrong = self.post_json(
            "login", {"username": "op", "password": PASSWORD, "role": "customer"}
        )
        assert wrong.status_code == 403

    def test_anonymous_cannot_use_my_chat(self):
        assert self.client.get(reverse("my-chat")).status_code == 403
        assert self.post_json("my-message", {"text": "hi"}).status_code == 403

    def test_operator_cannot_use_my_chat(self):
        self.client.force_login(self.operator)
        assert self.client.get(reverse("my-chat")).status_code == 403

    def test_chat_is_created_once_per_customer(self):
        self.client.force_login(self.customer)
        first = self.client.get(reverse("my-chat")).json()
        second = self.client.get(reverse("my-chat")).json()
        assert first["id"] == second["id"]
        assert Chat.objects.filter(customer=self.customer).count() == 1

    def test_message_is_saved_and_escalated(self):
        self.client.force_login(self.customer)
        response = self.post_json("my-message", {"text": "Де моя підписка?"})
        assert response.status_code == 201
        roles = [m["role"] for m in response.json()["messages"]]
        assert roles == ["customer", "ai"]
        assert response.json()["status"] == "needs_review"

    def test_customer_never_sees_another_customers_chat(self):
        self.client.force_login(self.other)
        self.post_json("my-message", {"text": "секрет"})
        self.client.force_login(self.customer)
        data = self.client.get(reverse("my-chat")).json()
        assert data["messages"] == []

    def test_customer_response_hides_internals(self):
        self.client.force_login(self.customer)
        data = self.post_json("my-message", {"text": "привіт"}).json()
        assert set(data) == {"id", "status", "messages"}

    def test_customer_cannot_read_operator_endpoints(self):
        self.client.force_login(self.customer)
        assert self.client.get(reverse("chat-list")).status_code == 403

    def test_empty_message_is_rejected(self):
        self.client.force_login(self.customer)
        assert self.post_json("my-message", {"text": "  "}).status_code == 400
