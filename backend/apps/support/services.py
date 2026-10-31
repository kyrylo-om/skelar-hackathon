"""Trusted backend services. AI calls require a server-issued turn token.

Call the provider/critic outside transactions. Lock order: conversation,
subscription, payment, action. No public arbitrary mutation endpoint.
"""
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.errors import Conflict
from apps.subscriptions.models import Payment, Subscription
from apps.support.models import Action, Conversation, Message
from apps.support.serializers import SubscriptionSerializer

LEASE_SECONDS = 45


def owned_conversation(user, conversation_id, *, lock=False):
    query = Conversation.objects.select_for_update() if lock else Conversation.objects
    return get_object_or_404(query, pk=conversation_id, user=user)


def check_turn(conversation, token, version):
    if (conversation.status != "ai" or conversation.version != version
            or conversation.in_flight_token != token or not token
            or not conversation.in_flight_at
            or conversation.in_flight_at <= timezone.now() - timedelta(seconds=LEASE_SECONDS)):
        raise Conflict("AI turn is stale or conversation is no longer in AI mode.")


def get_subscription(user):
    return SubscriptionSerializer(get_object_or_404(Subscription, user=user)).data


def get_payments(user):
    return list(Payment.objects.filter(user=user).values(
        "id", "plan_id", "status", "amount", "currency", "period_start", "period_end", "applied_at"))


@transaction.atomic
def begin_turn(user, conversation_id, text, client_message_id):
    conversation = owned_conversation(user, conversation_id, lock=True)
    existing = conversation.messages.filter(sender="customer", client_message_id=client_message_id).first()
    if existing:
        if existing.text != text:
            raise Conflict("client_message_id already belongs to another message.")
        if existing.response is not None:
            return conversation, existing, None
    if conversation.status == "resolved":
        raise Conflict("Conversation is resolved.")
    if (conversation.in_flight_token and conversation.in_flight_at
            and conversation.in_flight_at > timezone.now() - timedelta(seconds=LEASE_SECONDS)):
        raise Conflict("Another turn is in flight.")
    conversation.version += 1
    conversation.in_flight_token = uuid.uuid4() if conversation.status == "ai" else None
    conversation.in_flight_at = timezone.now() if conversation.in_flight_token else None
    conversation.save()
    message = existing or Message.objects.create(
        conversation=conversation, sender="customer", sender_user=user,
        text=text, client_message_id=client_message_id)
    return conversation, message, conversation.in_flight_token


@transaction.atomic
def finish_turn(user, conversation_id, token, version, text=None):
    conversation = owned_conversation(user, conversation_id, lock=True)
    check_turn(conversation, token, version)
    reply = None
    if text is not None:
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValidationError("Invalid assistant text.")
        reply = Message.objects.create(conversation=conversation, sender="assistant", text=text)
    conversation.in_flight_token = None
    conversation.in_flight_at = None
    conversation.save()
    return reply


@transaction.atomic
def handoff_to_operator(user, conversation_id, reason, *, token=None, version=None):
    conversation = owned_conversation(user, conversation_id, lock=True)
    # Customer/system paths omit token; AI callbacks must supply their turn token.
    if token is not None:
        check_turn(conversation, token, version)
    if conversation.status != "ai":
        return conversation
    subscription = Subscription.objects.filter(user=user).select_related("plan").first()
    facts = f"Plan: {subscription.plan.name}; version: {subscription.version}." if subscription else "No subscription."
    requests = list(conversation.messages.filter(sender="customer").order_by("-created_at").values_list("text", flat=True)[:3])
    actions = list(conversation.actions.values("kind", "status", "result"))
    conversation.summary = (f"Simulated billing. {facts}\nReason: {str(reason)[:1000]}\n"
                            f"Unresolved requests: {requests}\nAttempted actions: {actions}")[:6000]
    conversation.status = "waiting_operator"
    conversation.version += 1
    conversation.in_flight_token = None
    conversation.in_flight_at = None
    conversation.save()
    conversation.actions.filter(status__in=["proposed", "awaiting_confirmation"]).update(status="rejected")
    return conversation


def eligible_payment(user, payment, subscription):
    now = timezone.now()
    if (payment.user_id != user.pk or payment.status != "successful"
            or not payment.period_start <= now < payment.period_end):
        raise Conflict("Payment is not eligible for activation.")
    if Payment.objects.filter(user=user, status="successful").filter(
        Q(period_start__gt=payment.period_start)
        | Q(period_start=payment.period_start, created_at__gt=payment.created_at)
    ).exists():
        raise Conflict("Payment was superseded by a later purchase.")
    if subscription.period_end and subscription.period_end >= payment.period_end:
        raise Conflict("Payment cannot replace a newer or equal entitlement.")


@transaction.atomic
def propose_action(user, conversation_id, token, version, kind, payment_id=None):
    conversation = owned_conversation(user, conversation_id, lock=True)
    check_turn(conversation, token, version)
    subscription = get_object_or_404(Subscription.objects.select_for_update(), user=user)
    payment = None
    if kind == "sync_subscription":
        payment = get_object_or_404(Payment.objects.select_for_update(), pk=payment_id, user=user)
        if payment.applied_at:
            completed = Action.objects.filter(requesting_user=user, payment=payment, status="succeeded").first()
            if completed:
                return completed
            raise Conflict("Payment already applied.")
        eligible_payment(user, payment, subscription)
    elif kind == "cancel_auto_renewal":
        if payment_id is not None or not subscription.auto_renew:
            raise Conflict("Auto renewal is already disabled or parameters are invalid.")
    else:
        raise ValidationError("Unsupported action kind.")
    return Action.objects.create(
        conversation=conversation, requesting_user=user, subscription=subscription, payment=payment,
        kind=kind, parameters={"payment_id": str(payment.pk)} if payment else {},
        expected_version=subscription.version, conversation_version=version,
        expires_at=timezone.now() + timedelta(minutes=10),
        evidence={"subscription_id": str(subscription.pk), "subscription_version": subscription.version,
                  "payment_id": str(payment.pk) if payment else None},
    )


@transaction.atomic
def record_review(user, action_id, token, version, review):
    if (not isinstance(review, dict) or set(review) != {"decision", "reason", "missing_fields"}
            or review["decision"] not in ("allow", "ask_user", "handoff")
            or not isinstance(review["reason"], str) or not 0 < len(review["reason"]) <= 1000
            or not isinstance(review["missing_fields"], list)
            or any(not isinstance(v, str) for v in review["missing_fields"])):
        raise ValidationError("Malformed critic decision.")
    reference = get_object_or_404(Action, pk=action_id, requesting_user=user)
    conversation = owned_conversation(user, reference.conversation_id, lock=True)
    check_turn(conversation, token, version)
    action = Action.objects.select_for_update().get(pk=reference.pk)
    if (action.status != "proposed" or action.critic_decision
            or action.conversation_version != version or action.expires_at <= timezone.now()):
        raise Conflict("Proposal is stale.")
    action.critic_decision = review["decision"]
    action.critic_reason = review["reason"]
    if review["decision"] != "allow" or review["missing_fields"]:
        action.status = "rejected"
    elif action.kind == "cancel_auto_renewal":
        action.status = "awaiting_confirmation"
    action.save()
    return action


@transaction.atomic
def _execute(user, action_id, *, confirmation=False, token=None, version=None):
    reference = get_object_or_404(Action, pk=action_id, requesting_user=user)
    conversation = owned_conversation(user, reference.conversation_id, lock=True)
    subscription = get_object_or_404(Subscription.objects.select_for_update(), pk=reference.subscription_id, user=user)
    payment = None
    if reference.payment_id:
        payment = get_object_or_404(Payment.objects.select_for_update(), pk=reference.payment_id, user=user)
    action = Action.objects.select_for_update().get(pk=reference.pk)
    if action.status == "succeeded":
        return action, subscription, False
    if conversation.status != "ai":
        raise Conflict("AI actions are paused after handoff.")
    if action.expires_at <= timezone.now():
        raise Conflict("Action has expired.")
    if action.critic_decision != "allow" or action.expected_version != subscription.version:
        raise Conflict("Approval is missing or subscription has changed.")
    if action.kind == "cancel_auto_renewal":
        if not confirmation or action.status != "awaiting_confirmation" or not subscription.auto_renew:
            raise Conflict("Authenticated endpoint confirmation is required.")
        if conversation.in_flight_token:
            raise Conflict("Wait for the active turn to finish.")
        subscription.auto_renew = False
    elif action.kind == "sync_subscription":
        if confirmation:
            raise Conflict("This action does not accept customer confirmation.")
        check_turn(conversation, token, version)
        if action.conversation_version != version or action.status != "proposed":
            raise Conflict("Proposal belongs to another turn.")
        if payment.applied_at:
            raise Conflict("Payment already applied.")
        eligible_payment(user, payment, subscription)
        subscription.plan_id = payment.plan_id
        subscription.period_end = payment.period_end
        subscription.status = "active"
        payment.applied_at = timezone.now()
        payment.save(update_fields=["applied_at"])
    else:
        raise Conflict("Unsupported action.")
    subscription.version += 1
    subscription.save()
    action.status = "succeeded"
    action.result = {"subscription": dict(SubscriptionSerializer(subscription).data), "simulated_billing": True}
    action.save()
    return action, subscription, True


def execute_sync(user, action_id, token, version):
    return _execute(user, action_id, token=token, version=version)


def confirm_cancellation(user, action_id):
    reference = get_object_or_404(Action, pk=action_id, requesting_user=user)
    if reference.kind != "cancel_auto_renewal":
        raise Conflict("Only cancellation actions require endpoint confirmation.")
    return _execute(user, action_id, confirmation=True)


def propose_sync_subscription(user, conversation_id, token, version, payment_id):
    return propose_action(user, conversation_id, token, version, "sync_subscription", payment_id)


def propose_cancel_auto_renewal(user, conversation_id, token, version):
    return propose_action(user, conversation_id, token, version, "cancel_auto_renewal")
