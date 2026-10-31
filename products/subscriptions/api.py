"""Fake subscription-service backend: plans, pauses, cancellations, invoice refunds."""

import copy

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from supportkit.backend import body, error, mine, not_found, owned

SUBSCRIPTIONS = {
    "sub-1": {
        "id": "sub-1",
        "customer_id": 7,
        "plan": "Pro",
        "price": 299,
        "status": "active",
        "renews_on": "2026-11-15",
        "paused_months": 0,
    },
    "sub-2": {
        "id": "sub-2",
        "customer_id": 8,
        "plan": "Basic",
        "price": 149,
        "status": "active",
        "renews_on": "2026-11-20",
        "paused_months": 0,
    },
}

INVOICES = {
    "inv-501": {
        "id": "inv-501",
        "customer_id": 7,
        "subscription": "sub-1",
        "amount": 299,
        "refunded": 0,
        "issued_on": "2026-10-15",
    },
    "inv-502": {
        "id": "inv-502",
        "customer_id": 7,
        "subscription": "sub-1",
        "amount": 299,
        "refunded": 0,
        "issued_on": "2026-09-15",
    },
    "inv-601": {
        "id": "inv-601",
        "customer_id": 8,
        "subscription": "sub-2",
        "amount": 149,
        "refunded": 0,
        "issued_on": "2026-10-20",
    },
}


def create_app() -> Starlette:
    subscriptions = copy.deepcopy(SUBSCRIPTIONS)
    invoices = copy.deepcopy(INVOICES)

    async def list_subscriptions(request):
        return JSONResponse(mine(subscriptions, request))

    async def get_subscription(request):
        subscription = owned(subscriptions, request, "subscription_id")
        return JSONResponse(subscription) if subscription else not_found()

    async def pause(request):
        subscription = owned(subscriptions, request, "subscription_id")
        if subscription is None:
            return not_found()
        if subscription["status"] != "active":
            return error(409, "Призупинити можна лише активну підписку")
        months = (await body(request)).get("months")
        if months not in (1, 2, 3):
            return error(422, "Призупинити можна на 1–3 місяці")
        subscription["status"] = "paused"
        subscription["paused_months"] = months
        return JSONResponse(subscription)

    async def cancel(request):
        subscription = owned(subscriptions, request, "subscription_id")
        if subscription is None:
            return not_found()
        if subscription["status"] == "cancelled":
            return error(409, "Підписку вже скасовано")
        subscription["status"] = "cancelled"
        subscription["renews_on"] = None
        return JSONResponse(subscription)

    async def list_invoices(request):
        return JSONResponse(mine(invoices, request))

    async def refund(request):
        invoice = owned(invoices, request, "invoice_id")
        if invoice is None:
            return not_found()
        amount = (await body(request)).get("amount")
        if not isinstance(amount, (int, float)) or amount <= 0:
            return error(422, "Некоректна сума")
        if amount > invoice["amount"] - invoice["refunded"]:
            return error(409, "Сума більша за залишок до повернення")
        invoice["refunded"] += amount
        return JSONResponse(invoice)

    return Starlette(
        routes=[
            Route("/subscriptions", list_subscriptions),
            Route("/subscriptions/{subscription_id}", get_subscription),
            Route("/subscriptions/{subscription_id}/pause", pause, methods=["POST"]),
            Route("/subscriptions/{subscription_id}/cancel", cancel, methods=["POST"]),
            Route("/invoices", list_invoices),
            Route("/invoices/{invoice_id}/refund", refund, methods=["POST"]),
        ]
    )
