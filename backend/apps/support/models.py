from django.conf import settings
from django.db import models
from django.utils import timezone


class Chat(models.Model):
    class Status(models.TextChoices):
        NEEDS_REVIEW = "needs_review"
        AI_HANDLING = "ai_handling"
        RESOLVED = "resolved"

    class Priority(models.TextChoices):
        LOW = "low"
        NORMAL = "normal"
        HIGH = "high"

    customer_name = models.CharField(max_length=120)
    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status, default=Status.AI_HANDLING)
    priority = models.CharField(max_length=10, choices=Priority, default=Priority.NORMAL)
    summary = models.TextField(blank=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"#{self.pk} {self.customer_name}: {self.subject}"


class Message(models.Model):
    class Role(models.TextChoices):
        CUSTOMER = "customer"
        AI = "ai"
        OPERATOR = "operator"
        SYSTEM = "system"

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role)
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.role}: {self.text[:40]}"


class TraceStep(models.Model):
    class Agent(models.TextChoices):
        GUARD = "guard"
        TRIAGE = "triage"
        ACTOR = "actor"
        CRITIC = "critic"
        POLICY = "policy"
        EXECUTOR = "executor"
        QA = "qa"

    class Verdict(models.TextChoices):
        PASS = "pass"
        BLOCK = "block"
        INFO = "info"

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="trace")
    agent = models.CharField(max_length=10, choices=Agent)
    verdict = models.CharField(max_length=10, choices=Verdict)
    detail = models.TextField()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.agent}: {self.verdict}"


class ReviewItem(models.Model):
    class Risk(models.TextChoices):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="reviews")
    action = models.CharField(max_length=60)
    params = models.JSONField(default=dict, blank=True)
    risk = models.CharField(max_length=10, choices=Risk)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.action} ({self.status})"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    event = models.CharField(max_length=60)
    chat = models.ForeignKey(
        Chat, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.event} #{self.pk}"
