"""Facts about one customer, read from the product. The model never writes any of this.

Two views of the same data: `load_facts` is what the Actor and Critic read (JSON-friendly), and
`policy_ctx` is the lookup Policy uses for ownership, status and payment checks.
"""

from apps.subscriptions.models import Payment, Subscription

MAX_PAYMENTS = 10


def _date(value) -> str | None:
    return value.date().isoformat() if value else None


def load_facts(user) -> dict:
    subscription = Subscription.objects.select_related("plan").filter(user=user).first()
    payments = (Payment.objects.filter(user=user).select_related("plan").order_by("-created_at"))[
        :MAX_PAYMENTS
    ]
    return {
        "subscription": None
        if subscription is None
        else {
            "id": str(subscription.pk),
            "plan": subscription.plan.name,
            "status": subscription.status,
            "auto_renew": subscription.auto_renew,
            "period_end": _date(subscription.period_end),
        },
        "payments": [
            {
                "id": str(p.pk),
                "plan": p.plan.name,
                "amount": float(p.amount),
                "currency": p.currency,
                "status": p.status,
                "applied": p.applied_at is not None,
                "period_end": _date(p.period_end),
            }
            for p in payments
        ],
    }


def policy_ctx(user, facts: dict) -> dict:
    ctx = {
        "payments": {
            p["id"]: {
                "customer_id": user.pk,
                "confirmed": p["status"] == "successful",
                "applied": p["applied"],
                "amount": p["amount"],
            }
            for p in facts["payments"]
        },
        "subscriptions": {},
        "vip": False,
    }
    if facts["subscription"]:
        ctx["subscriptions"][facts["subscription"]["id"]] = {"customer_id": user.pk}
    return ctx
