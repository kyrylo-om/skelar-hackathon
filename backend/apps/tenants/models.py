from django.conf import settings
from django.db import models
from django.utils import timezone


class TenantCustomer(models.Model):
    """Who this logged-in user is inside a connected product. Set by us, never by the customer."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tenant_customer"
    )
    tenant = models.CharField(max_length=40)  # the product's key in execution/products.toml
    external_id = models.CharField(max_length=80)  # the customer's id in that product

    def __str__(self):
        return f"{self.user_id} is {self.tenant}/{self.external_id}"


class ApiCall(models.Model):
    """One call the agent side made to a product: read, proposal or execution.

    Secrets are masked.
    """

    READ = "read"
    PROPOSE = "propose"
    EXECUTE = "execute"
    REJECT = "reject"

    tenant = models.CharField(max_length=40)
    customer = models.CharField(max_length=80, blank=True)
    chat = models.ForeignKey(
        "review.Chat", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    kind = models.CharField(max_length=10)
    endpoint_id = models.CharField(max_length=80, blank=True)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=500)
    status = models.CharField(max_length=24, blank=True)  # http status or proposal status
    duration_ms = models.PositiveIntegerField(default=0)
    initiator = models.CharField(max_length=24, default="agent")  # agent | policy | operator
    request = models.JSONField(default=dict, blank=True)
    response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.kind} {self.method} {self.path} -> {self.status}"
