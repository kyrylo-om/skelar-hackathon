from django.db import models
from django.utils import timezone


class SecurityEvent(models.Model):
    """An input Guard refused. The dashboard lists these as blocked attacks."""

    customer_id = models.IntegerField(null=True, blank=True)
    text = models.TextField()
    rule = models.CharField(max_length=80)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.rule} (customer {self.customer_id})"


class ActionLog(models.Model):
    """Actions that were allowed to run, used by Policy for rate limits and idempotency."""

    customer_id = models.IntegerField(db_index=True)
    action = models.CharField(max_length=60)
    params_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.action} (customer {self.customer_id})"
