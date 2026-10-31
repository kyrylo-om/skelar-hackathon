"""Policy Engine: plain code, no LLM. Nothing a model says can change a decision here.

`evaluate` runs every check and returns the strictest outcome (deny > needs_review > allow);
among equally strict outcomes the earliest rule in the order below wins.

`ctx` carries the facts about this customer, supplied by the caller (never by the message):
    {"orders":        {"1042": {"customer_id": 7, "status": "processing", "total": 420}},
     "subscriptions": {"s1":   {"customer_id": 7}},
     "payments":      {"p1":   {"customer_id": 7, "confirmed": True, "applied": False}},
     "vip": False}

`mode="after_human_approval"` is used when an operator has already approved the action: the review
bands (auto limit, risk, VIP, always-review) and the rate limit are skipped, everything else,
including the hard limits, is checked again against fresh facts.
"""

import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .contracts import ALLOW, DENY, NEEDS_REVIEW, PolicyResult
from .models import ActionLog

NORMAL = "normal"
AFTER_APPROVAL = "after_human_approval"

# Local registry until the manifest loader replaces it.
# `required` maps a parameter to its type; "amount" is a positive number.
ACTIONS = {
    "get_order_status": {"risk": "low", "required": {"order": str}},
    "change_address": {"risk": "medium", "required": {"order": str, "address": str}},
    "cancel_order": {"risk": "medium", "required": {"order": str}},
    "issue_refund": {"risk": "medium", "required": {"order": str, "amount": "amount"}},
    "pause_subscription": {"risk": "low", "required": {"subscription": str}},
    "cancel_subscription": {"risk": "medium", "required": {"subscription": str}},
    "escalate_to_human": {"risk": "low", "required": {}, "always_review": True},
    "change_payment_method": {"risk": "high", "required": {}},
    # Cloud-storage domain (apps.subscriptions).
    "get_subscription": {"risk": "low", "required": {}},
    "get_payments": {"risk": "low", "required": {}},
    "sync_subscription": {
        "risk": "medium",
        "required": {"payment_id": str},
        "payment_check": True,
    },
    "cancel_auto_renewal": {"risk": "medium", "required": {}},
}
PROCESSING_ONLY = {"cancel_order", "change_address"}
# Which context table owns an object named by this parameter.
OWNED = {
    "order": "orders",
    "order_id": "orders",
    "subscription": "subscriptions",
    "subscription_id": "subscriptions",
    "payment_id": "payments",
    "invoice_id": "invoices",
}
RANK = {ALLOW: 0, NEEDS_REVIEW: 1, DENY: 2}


def params_hash(action: str, params: dict) -> str:
    raw = json.dumps([action, params], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _deny(rule: str, reason: str) -> PolicyResult:
    return PolicyResult(DENY, rule, reason)


def _review(rule: str, reason: str) -> PolicyResult:
    return PolicyResult(NEEDS_REVIEW, rule, reason)


def _check_registry(customer_id, action, params, ctx):
    if action not in ACTIONS:
        return _deny("unknown_action", f"Дія {action} не дозволена")


def _check_params(customer_id, action, params, ctx):
    for name, kind in ACTIONS[action]["required"].items():
        value = params.get(name)
        if kind == "amount":
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        else:
            ok = isinstance(value, kind) and bool(value.strip())
        if not ok:
            return _deny("invalid_params", f"Параметр {name} відсутній або некоректний")


def _check_ownership(customer_id, action, params, ctx):
    # A missing record and someone else's record look the same, so nothing leaks.
    for key, table in OWNED.items():
        if isinstance(params.get(key), str):
            record = ctx.get(table, {}).get(params[key])
            if record is None or record.get("customer_id") != customer_id:
                return _deny("ownership", "Об'єкт не належить цьому клієнту")


def _check_payment(customer_id, action, params, ctx):
    if not ACTIONS[action].get("payment_check"):
        return None
    payment = ctx.get("payments", {}).get(params.get("payment_id"), {})
    if not payment.get("confirmed") or payment.get("applied"):
        return _deny("payment_not_confirmed", "Платіж не підтверджений або вже використаний")


def _check_status(customer_id, action, params, ctx):
    if action in PROCESSING_ONLY:
        order = ctx.get("orders", {}).get(params.get("order"), {})
        if order.get("status") != "processing":
            return _deny("status", "Дія можлива лише для замовлення в обробці")


def _check_amount(customer_id, action, params, ctx):
    if action != "issue_refund":
        return None
    amount = params["amount"]
    order = ctx.get("orders", {}).get(params["order"], {})
    if "total" in order and amount > order["total"]:
        return _deny("amount_exceeds_order", "Сума повернення більша за суму замовлення")
    if amount > settings.HARD_REFUND_LIMIT:
        return _deny("refund_hard_limit", f"Сума перевищує ліміт {settings.HARD_REFUND_LIMIT} грн")
    if amount > settings.AUTO_REFUND_LIMIT:
        return _review("refund_auto_limit", f"Сума {amount} грн вища за автоліміт")


def _check_daily_total(customer_id, action, params, ctx):
    """Many small refunds must not add up past the daily cap."""
    if action != "issue_refund":
        return None
    since = timezone.now() - timedelta(hours=24)
    spent = (
        ActionLog.objects.filter(
            customer_id=customer_id, action=action, created_at__gte=since
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    if spent + params["amount"] > settings.DAILY_REFUND_LIMIT:
        return _deny("daily_limit", f"Перевищено добовий ліміт {settings.DAILY_REFUND_LIMIT} грн")


def _check_rate_limit(customer_id, action, params, ctx):
    if ACTIONS[action]["risk"] == "low":
        return None
    since = timezone.now() - timedelta(hours=1)
    risky = [name for name, spec in ACTIONS.items() if spec["risk"] != "low"]
    recent = ActionLog.objects.filter(
        customer_id=customer_id, action__in=risky, created_at__gte=since
    ).count()
    if recent >= settings.RISKY_ACTIONS_PER_HOUR:
        return _deny("rate_limit", "Забагато ризикових дій за годину")


def _check_idempotency(customer_id, action, params, ctx):
    since = timezone.now() - timedelta(seconds=settings.IDEMPOTENCY_WINDOW_SEC)
    if ActionLog.objects.filter(
        customer_id=customer_id,
        action=action,
        params_hash=params_hash(action, params),
        created_at__gte=since,
    ).exists():
        return _deny("idempotency", "Така сама дія вже виконувалась щойно")


def _check_risk(customer_id, action, params, ctx):
    spec = ACTIONS[action]
    if spec.get("always_review"):
        return _review("human_requested", "Запит передано людині")
    if settings.POLICY_REVIEW_HIGH_RISK and spec["risk"] == "high":
        return _review("high_risk", "Дія високого ризику потребує людини")
    if settings.POLICY_REVIEW_VIP and ctx.get("vip") and spec["risk"] != "low":
        return _review("vip", "Клієнт VIP: рішення за людиною")


CHECKS = [
    _check_registry,
    _check_params,
    _check_ownership,
    _check_payment,
    _check_status,
    _check_amount,
    _check_daily_total,
    _check_rate_limit,
    _check_idempotency,
    _check_risk,
]


def evaluate(
    customer_id: int, action: str, params: dict, ctx: dict | None = None, mode: str = NORMAL
) -> PolicyResult:
    if mode not in (NORMAL, AFTER_APPROVAL):
        return _deny("bad_mode", "Невідомий режим перевірки")
    ctx = ctx or {}
    params = params if isinstance(params, dict) else {}
    strictest = PolicyResult(ALLOW, "ok", "Усі перевірки пройдено")
    try:
        for check in CHECKS:
            result = check(customer_id, action, params, ctx)
            if result is None:
                continue
            # A human already decided the review bands; only hard failures remain.
            if mode == AFTER_APPROVAL and (
                result.decision == NEEDS_REVIEW or result.rule == "rate_limit"
            ):
                continue
            if RANK[result.decision] > RANK[strictest.decision]:
                strictest = result
            # Later checks index into the registry and params, so stop on a hard failure.
            if result.rule in ("unknown_action", "invalid_params"):
                break
    except Exception:  # noqa: BLE001 - fail closed on any bug in a rule
        return _deny("policy_error", "Не вдалося перевірити дію")
    return strictest


def record(customer_id: int, action: str, params: dict) -> None:
    """Remember an action that was allowed, for rate limits, repeats and the daily total."""
    amount = params.get("amount")
    ActionLog.objects.create(
        customer_id=customer_id,
        action=action,
        params_hash=params_hash(action, params),
        amount=amount
        if isinstance(amount, (int, float)) and not isinstance(amount, bool)
        else None,
    )
