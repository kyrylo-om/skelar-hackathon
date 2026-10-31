"""Run on PostgreSQL; SQLite cannot validate row-lock semantics."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.subscriptions.models import Payment, Plan, Subscription
from apps.support import services
from apps.support.models import Conversation

pytestmark = pytest.mark.django_db(transaction=True)


def require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks and independent connections")


def test_concurrent_sync_applies_once():
    require_postgres()
    user = get_user_model().objects.create_user("concurrent-customer")
    plan = Plan.objects.create(name="Plus", price=99, storage_limit_gb=100)
    sub = Subscription.objects.create(user=user, plan=plan)
    payment = Payment.objects.create(
        user=user,
        plan=plan,
        amount=99,
        status="successful",
        period_start=timezone.now() - timedelta(days=1),
        period_end=timezone.now() + timedelta(days=29),
    )
    conversation = Conversation.objects.create(user=user)
    turn, _, token = services.begin_turn(user, conversation.pk, "Activate", "sync")
    action = services.propose_action(
        user, conversation.pk, token, turn.version, "sync_subscription", payment.pk
    )
    services.record_review(
        user,
        action.pk,
        token,
        turn.version,
        {"decision": "allow", "reason": "Verified payment", "missing_fields": []},
    )
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        try:
            actor = get_user_model().objects.get(pk=user.pk)
            barrier.wait(timeout=10)
            return services.execute_sync(actor, action.pk, token, turn.version)[2]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))
    assert sorted(results) == [False, True]
    sub.refresh_from_db()
    payment.refresh_from_db()
    assert sub.version == 1 and sub.period_end == payment.period_end and payment.applied_at


def test_concurrent_operator_claim_is_exclusive():
    require_postgres()
    user = get_user_model().objects.create_user("customer")
    operators = [get_user_model().objects.create_user(f"staff{i}", is_staff=True) for i in range(2)]
    conversation = Conversation.objects.create(user=user, status="waiting_operator")
    barrier = Barrier(2)

    def worker(operator_id):
        close_old_connections()
        try:
            api = APIClient()
            api.force_authenticate(user=get_user_model().objects.get(pk=operator_id))
            barrier.wait(timeout=10)
            return api.post(
                f"/api/operator/conversations/{conversation.pk}/claim/", {}, format="json"
            ).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, [operator.pk for operator in operators]))
    assert sorted(results) == [200, 409]
