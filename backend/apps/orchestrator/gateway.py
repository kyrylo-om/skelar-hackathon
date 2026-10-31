"""The only door from the orchestrator to the product's write side.

`DevDomainGateway` drives the Cloud Support domain (apps.subscriptions and apps.support) through its
trusted services. Their `Conversation` is used purely as a hidden action ledger: one open turn
(with its lease, version and token) per run, so every change is recorded and idempotent there. The
model never reaches any of this: the pipeline calls the gateway only after Gate said "execute".
"""

import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import APIException

from apps.support import services as support
from apps.support.models import Action, Conversation

from . import facts as product

DONE = "done"
AWAITING = "awaiting_confirmation"
FAILED = "failed"

SUPPORTED = ("get_subscription", "get_payments", "sync_subscription", "cancel_auto_renewal")


class Busy(Exception):
    """Another turn is still running for this customer."""


@dataclass
class ActionOutcome:
    action: str
    status: str
    facts: dict = field(default_factory=dict)
    action_id: str | None = None
    error: str = ""


@dataclass(frozen=True)
class Turn:
    conversation_id: object
    token: object
    version: int


def _message(exc: Exception) -> str:
    if isinstance(exc, Http404):
        return "Об'єкт не знайдено"
    detail = getattr(exc, "detail", None)
    if isinstance(detail, (list, dict)):
        detail = str(detail)
    return str(detail or exc)[:300]


class DevDomainGateway:
    def __init__(self, user):
        self.user = user

    def load_facts(self) -> dict:
        return product.load_facts(self.user)

    def _ledger(self) -> Conversation:
        conversation = Conversation.objects.filter(user=self.user, status="ai").first()
        return conversation or Conversation.objects.create(user=self.user)

    def hand_off(self) -> int:
        """The customer's conversation moved to a human: nothing the AI proposed may be confirmed.

        Open turns are invalidated (the version moves on) and every proposed or waiting action is
        rejected, so a stale confirm button or a late AI callback finds nothing to act on.
        Returns the number of actions that were rejected.
        """
        with transaction.atomic():
            for ledger in Conversation.objects.select_for_update().filter(
                user=self.user, status="ai"
            ):
                ledger.version += 1
                ledger.in_flight_token = None
                ledger.in_flight_at = None
                ledger.save()
            return Action.objects.filter(
                requesting_user=self.user, status__in=["proposed", "awaiting_confirmation"]
            ).update(status="rejected")

    @contextmanager
    def turn(self, label: str = "orchestrator turn"):
        """Open a turn on the ledger; always release it, even when the work failed."""
        ledger = self._ledger()
        try:
            conversation, _, token = support.begin_turn(
                self.user, ledger.pk, label, str(uuid.uuid4())
            )
        except APIException as exc:
            raise Busy(_message(exc)) from exc
        if token is None:
            raise Busy("AI turn is not available")
        turn = Turn(conversation.pk, token, conversation.version)
        try:
            yield turn
        finally:
            try:
                support.finish_turn(self.user, turn.conversation_id, turn.token, turn.version)
            except APIException:
                pass  # the lease simply expires

    def run(
        self, turn: Turn, action: str, params: dict, facts: dict, reason: str = ""
    ) -> ActionOutcome:
        if action not in SUPPORTED:
            return ActionOutcome(action, FAILED, error="Дію не підтримує підключений продукт")
        if action in ("get_subscription", "get_payments"):
            return ActionOutcome(action, DONE, facts=facts)
        subscription = facts.get("subscription")
        if action == "cancel_auto_renewal" and subscription and not subscription["auto_renew"]:
            return ActionOutcome(action, DONE, facts={"already": True})  # nothing to change
        try:
            if action == "sync_subscription":
                return self._sync(turn, params, reason)
            return self._cancel_renewal(turn, reason)
        except (APIException, Http404) as exc:
            return ActionOutcome(action, FAILED, error=_message(exc))

    def _approve(self, turn: Turn, proposed, reason: str):
        review = {
            "decision": "allow",
            "reason": reason or "Critic approved the plan",
            "missing_fields": [],
        }
        return support.record_review(self.user, proposed.pk, turn.token, turn.version, review)

    def _sync(self, turn: Turn, params: dict, reason: str) -> ActionOutcome:
        proposed = support.propose_sync_subscription(
            self.user, turn.conversation_id, turn.token, turn.version, params["payment_id"]
        )
        if proposed.status == "succeeded":  # an earlier turn already applied it
            return ActionOutcome("sync_subscription", DONE, action_id=str(proposed.pk))
        approved = self._approve(turn, proposed, reason)
        if approved.status != "proposed":
            return ActionOutcome("sync_subscription", FAILED, error="Дію відхилено перевіркою")
        action, subscription, _changed = support.execute_sync(
            self.user, approved.pk, turn.token, turn.version
        )
        return ActionOutcome(
            "sync_subscription",
            DONE,
            facts={
                "plan": subscription.plan.name,
                "period_end": subscription.period_end.date().isoformat(),
            },
            action_id=str(action.pk),
        )

    def _cancel_renewal(self, turn: Turn, reason: str) -> ActionOutcome:
        proposed = support.propose_cancel_auto_renewal(
            self.user, turn.conversation_id, turn.token, turn.version
        )
        approved = self._approve(turn, proposed, reason)
        if approved.status != "awaiting_confirmation":
            return ActionOutcome("cancel_auto_renewal", FAILED, error="Дію відхилено перевіркою")
        # Only the customer's own button (an authenticated endpoint) can confirm this one.
        return ActionOutcome("cancel_auto_renewal", AWAITING, action_id=str(approved.pk))
