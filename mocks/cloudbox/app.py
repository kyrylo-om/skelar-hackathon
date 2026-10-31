"""CloudBox mock: the API described in context.md, on SQLite, plus the customer portal."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mocks.common import Auth, Database, body, error, portal_routes

HERE = Path(__file__).parent
DB = HERE / "cloudbox.sqlite3"
SUBSCRIPTION = """
    SELECT s.id, s.status, s.period_end, s.auto_renew, p.name AS plan, p.price, p.storage_gb
    FROM subscriptions s JOIN plans p ON p.id = s.plan_id
    WHERE s.customer_id = ?
"""
PAYMENTS = """
    SELECT p.id, pl.name AS plan, p.amount, p.status, p.period_days, p.created_at,
           p.applied_at, p.refunded
    FROM payments p JOIN plans pl ON pl.id = p.plan_id
    WHERE p.customer_id = ?
"""


def create_app(db_path: Path | None = None, api_key: str | None = None) -> Starlette:
    db = Database(db_path or DB, HERE / "context.md", HERE / "seed.sql")
    auth = Auth(api_key or os.environ.get("CLOUDBOX_API_KEY", "cloudbox-dev-key"), db)

    def subscription(customer: str) -> dict:
        row = db.one(SUBSCRIPTION, customer)
        return row | {"auto_renew": bool(row["auto_renew"])}

    @auth.required
    async def me(request, customer):
        return JSONResponse(db.one("SELECT * FROM customers WHERE id = ?", customer))

    @auth.required
    async def get_subscription(request, customer):
        return JSONResponse(subscription(customer))

    @auth.required
    async def payments(request, customer):
        return JSONResponse(db.all(PAYMENTS + " ORDER BY p.created_at DESC", customer))

    @auth.required
    async def sync(request, customer):
        payment = db.one(
            PAYMENTS + " AND p.id = ?", customer, str((await body(request)).get("payment_id"))
        )
        if payment is None:
            return error(404, "Payment not found")
        if payment["status"] != "successful":
            return error(409, "Only a successful payment can be applied")
        current = subscription(customer)
        now = datetime.now(UTC)
        start = now
        if current["plan"] == payment["plan"] and current["period_end"]:
            start = max(now, datetime.fromisoformat(current["period_end"]))
        period_end = (start + timedelta(days=payment["period_days"])).isoformat(timespec="seconds")
        with db.transaction() as tx:
            applied = tx.execute(
                "UPDATE payments SET applied_at = ? WHERE id = ? AND applied_at IS NULL",
                (now.isoformat(timespec="seconds"), payment["id"]),
            )
            if applied.rowcount == 0:
                return error(409, "The payment is already applied")
            tx.execute(
                "UPDATE subscriptions SET plan_id = (SELECT plan_id FROM payments WHERE id = ?),"
                " status = 'active', period_end = ? WHERE customer_id = ?",
                (payment["id"], period_end, customer),
            )
        return JSONResponse(subscription(customer))

    def set_renewal(value: int):
        @auth.required
        async def endpoint(request, customer):
            with db.transaction() as tx:
                tx.execute(
                    "UPDATE subscriptions SET auto_renew = ? WHERE customer_id = ?",
                    (value, customer),
                )
            return JSONResponse(subscription(customer))

        return endpoint

    @auth.required
    async def refund(request, customer):
        payment = db.one(PAYMENTS + " AND p.id = ?", customer, request.path_params["payment_id"])
        if payment is None:
            return error(404, "Payment not found")
        if payment["status"] != "successful":
            return error(409, "Only a successful payment can be refunded")
        amount = (await body(request)).get("amount")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
            return error(422, "amount must be a positive number")
        with db.transaction() as tx:
            refunded = tx.execute(
                "UPDATE payments SET refunded = refunded + ?"
                " WHERE id = ? AND refunded + ? <= amount",
                (amount, payment["id"], amount),
            )
            if refunded.rowcount == 0:
                return error(409, "The amount is more than what is left to refund")
        return JSONResponse(db.one(PAYMENTS + " AND p.id = ?", customer, payment["id"]))

    return Starlette(
        routes=[
            *portal_routes(HERE / "portal.html", db, "cloudbox"),
            Route("/me", me),
            Route("/subscription", get_subscription),
            Route("/payments", payments),
            Route("/subscription/sync", sync, methods=["POST"]),
            Route("/subscription/auto-renewal/off", set_renewal(0), methods=["POST"]),
            Route("/subscription/auto-renewal/on", set_renewal(1), methods=["POST"]),
            Route("/payments/{payment_id}/refund", refund, methods=["POST"]),
        ]
    )
