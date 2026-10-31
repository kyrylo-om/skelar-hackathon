from django.db import transaction
from django.utils import timezone

from . import ports
from .models import AuditLog, Chat, Message, ReviewItem, TraceStep


class ReviewAlreadyDecided(Exception):
    pass


def _touch(chat: Chat) -> None:
    chat.updated_at = timezone.now()
    chat.save(update_fields=["updated_at"])


def add_message(chat: Chat, role: str, text: str) -> Message:
    message = Message.objects.create(chat=chat, role=role, text=text)
    _touch(chat)
    return message


def open_review(chat: Chat, *, action: str, params: dict, risk: str, reason: str) -> ReviewItem:
    """Entry point for the agent pipeline: put an action in front of a human."""
    review = ReviewItem.objects.create(
        chat=chat, action=action, params=params, risk=risk, reason=reason
    )
    chat.status = Chat.Status.NEEDS_REVIEW
    chat.save(update_fields=["status"])
    _touch(chat)
    return review


def add_trace(chat: Chat, steps: list[dict]) -> None:
    TraceStep.objects.bulk_create(TraceStep(chat=chat, **step) for step in steps)


def reply_as_operator(chat: Chat, operator, text: str) -> Message:
    message = add_message(chat, Message.Role.OPERATOR, text)
    AuditLog.objects.create(
        actor=operator, event="operator_reply", chat=chat, payload={"message_id": message.pk}
    )
    return message


@transaction.atomic
def decide_review(review_id: int, operator, decision: str, note: str = "") -> ReviewItem:
    review = ReviewItem.objects.select_for_update().select_related("chat").get(pk=review_id)
    if review.status != ReviewItem.Status.PENDING:
        raise ReviewAlreadyDecided(review_id)

    if decision == ReviewItem.Status.APPROVED:
        # A failure here rolls the transaction back and leaves the review pending.
        ports.execute(review.action, review.params)

    review.status = decision
    review.decided_by = operator
    review.decided_at = timezone.now()
    review.note = note
    review.save()

    chat = review.chat
    if not chat.reviews.filter(status=ReviewItem.Status.PENDING).exists():
        chat.status = Chat.Status.RESOLVED
        chat.save(update_fields=["status"])
    verb = "схвалив" if decision == ReviewItem.Status.APPROVED else "відхилив"
    add_message(chat, Message.Role.SYSTEM, f"Оператор {verb} дію {review.action}")
    AuditLog.objects.create(
        actor=operator,
        event=f"review_{decision}",
        chat=chat,
        payload={"review_id": review.pk, "action": review.action, "params": review.params},
    )
    return review
