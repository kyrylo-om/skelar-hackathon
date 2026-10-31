import uuid

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=24,
        default="ai",
        choices=[(s, s) for s in ("ai", "waiting_operator", "operator", "resolved")],
    )
    assigned_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assigned_conversations",
    )
    summary = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=0)
    in_flight_token = models.UUIDField(null=True, blank=True)
    in_flight_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.CharField(
        max_length=16, choices=[(s, s) for s in ("customer", "assistant", "operator", "system")]
    )
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    text = models.TextField()
    client_message_id = models.CharField(max_length=128, null=True, blank=True)
    response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "sender", "client_message_id"], name="unique_client_message"
            )
        ]


class Action(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="actions")
    requesting_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    subscription = models.ForeignKey("subscriptions.Subscription", on_delete=models.PROTECT)
    payment = models.ForeignKey(
        "subscriptions.Payment", on_delete=models.PROTECT, null=True, blank=True
    )
    kind = models.CharField(
        max_length=32,
        choices=[
            ("sync_subscription", "sync_subscription"),
            ("cancel_auto_renewal", "cancel_auto_renewal"),
        ],
    )
    parameters = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32,
        default="proposed",
        choices=[
            (s, s)
            for s in (
                "proposed",
                "awaiting_confirmation",
                "executing",
                "succeeded",
                "failed",
                "rejected",
                "expired",
            )
        ],
    )
    expires_at = models.DateTimeField()
    expected_version = models.PositiveIntegerField()
    conversation_version = models.PositiveIntegerField()
    critic_decision = models.CharField(max_length=16, blank=True)
    critic_reason = models.CharField(max_length=1000, blank=True)
    evidence = models.JSONField(default=dict)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
