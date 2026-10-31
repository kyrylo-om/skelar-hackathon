from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.support import ports, services
from apps.support.models import AuditLog, Chat, ReviewItem
from apps.support.permissions import OPERATOR_GROUP

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
