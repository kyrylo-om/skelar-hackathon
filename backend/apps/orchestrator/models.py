import uuid

from django.conf import settings
from django.db import models


class TurnState(models.Model):
    """What the pipeline remembers between a customer's messages in one chat."""

    chat = models.OneToOneField("review.Chat", on_delete=models.CASCADE, related_name="turn_state")
    clarifications_used = models.PositiveSmallIntegerField(default=0)
    last_intent = models.CharField(max_length=60, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"chat {self.chat_id}: {self.clarifications_used} clarifications"


class ProductConfirmation(models.Model):
    """A change proposed to an external product, waiting for the customer's own confirm button.

    `proposal_id` names the stored call on the execution server; only the confirm endpoint, a
    request from this customer, can make it run.
    """

    class Status(models.TextChoices):
        AWAITING = "awaiting_confirmation"
        CONFIRMING = "confirming"
        DONE = "succeeded"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    action = models.CharField(max_length=60)
    params = models.JSONField(default=dict, blank=True)
    proposal_id = models.CharField(max_length=64)
    status = models.CharField(max_length=24, choices=Status, default=Status.AWAITING)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"{self.action} for {self.customer_id}: {self.status}"
