import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.review import services as review_services
from apps.security.llm import mock as llm_mock
from apps.subscriptions.models import Payment, Plan, Subscription

REAL_RESPOND = llm_mock.respond
User = get_user_model()


def make_customer(username="cust", *, payment=True, subscription=True, applied=False):
    """A customer on the Free plan, optionally with a paid but unapplied Plus payment."""
    user = User.objects.create_user(username, password="synthetic-pass-123")
    free, _ = Plan.objects.get_or_create(name="Free", defaults={"price": 0, "storage_limit_gb": 5})
    plus, _ = Plan.objects.get_or_create(
        name="Plus", defaults={"price": 99, "storage_limit_gb": 100}
    )
    now = timezone.now()
    if subscription:
        Subscription.objects.create(user=user, plan=free, auto_renew=True)
    paid = None
    if payment:
        paid = Payment.objects.create(
            user=user,
            plan=plus,
            amount=99,
            status="successful",
            period_start=now - timedelta(days=1),
            period_end=now + timedelta(days=29),
            applied_at=now if applied else None,
        )
    return user, paid


def send(user, text):
    """Send a customer message through the real path: review service, ports, orchestrator."""
    chat = review_services.chat_for_customer(user)
    review_services.receive_customer_message(chat, text)
    chat.refresh_from_db()
    return chat


def last_reply(chat):
    return chat.messages.filter(role="ai").order_by("-id").first().text


def agents(chat):
    return [step.agent for step in chat.trace.all()]


def patch_roles(**by_role):
    """Replace the mock model's answer for some roles; the rest keep the real mock behaviour.

    Each value is a dict (sent as JSON), a string (sent as is) or a callable of the user message.
    """

    def respond(role, system, user):
        if role in by_role:
            value = by_role[role]
            value = value(user) if callable(value) else value
            return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return REAL_RESPOND(role, system, user)

    return mock.patch.object(llm_mock, "respond", side_effect=respond)
