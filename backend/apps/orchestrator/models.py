from django.db import models


class TurnState(models.Model):
    """What the pipeline remembers between a customer's messages in one chat."""

    chat = models.OneToOneField("review.Chat", on_delete=models.CASCADE, related_name="turn_state")
    clarifications_used = models.PositiveSmallIntegerField(default=0)
    last_intent = models.CharField(max_length=60, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"chat {self.chat_id}: {self.clarifications_used} clarifications"
