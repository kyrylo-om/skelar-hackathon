import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=32, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="UAH")
    storage_limit_gb = models.PositiveIntegerField()


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=16, default="active", choices=[("active", "active"), ("inactive", "inactive")]
    )
    period_end = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=0)


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="UAH")
    status = models.CharField(
        max_length=16,
        choices=[("successful", "successful"), ("failed", "failed"), ("pending", "pending")],
    )
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    demo_reference = models.CharField(max_length=64, unique=True, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(period_end__gt=F("period_start")), name="payment_positive_period"
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="payment_nonnegative_amount"),
        ]
