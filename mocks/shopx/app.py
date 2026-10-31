"""ShopX mock: the API described in context.md, on SQLite, plus the customer portal."""

import os
from datetime import UTC, datetime
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mocks.common import Auth, Database, body, error, portal_routes

HERE = Path(__file__).parent
DB = Path(os.environ.get("MOCK_DATA_DIR", HERE)) / "shopx.sqlite3"
ORDER = "SELECT * FROM orders WHERE customer_id = ?"


def create_app(db_path: Path | None = None, api_key: str | None = None) -> Starlette:
    db = Database(db_path or DB, HERE / "context.md", HERE / "seed.sql")
    auth = Auth(api_key or os.environ.get("SHOPX_API_KEY", "shopx-dev-key"), db)

    def order(customer: str, number: str) -> dict | None:
        row = db.one(ORDER + " AND number = ?", customer, number)
        if row is None:
            return None
        items = db.all(
            "SELECT title, quantity, price FROM order_items WHERE order_number = ?", number
        )
        refunds = db.all(
            "SELECT amount, reason, created_at FROM refunds WHERE order_number = ?", number
        )
        return row | {"items": items, "refunds": refunds}

    def update_processing(customer: str, number: str, change: str, sql: str, params: tuple):
        """Apply an update that only a processing order accepts."""
        if order(customer, number) is None:
            return error(404, "Order not found")
        with db.transaction() as tx:
            if tx.execute(sql + " AND status = 'processing'", params).rowcount == 0:
                return error(409, f"Only a processing order can be {change}")
        return JSONResponse(order(customer, number))

    @auth.required
    async def me(request, customer):
        return JSONResponse(db.one("SELECT * FROM customers WHERE id = ?", customer))

    @auth.required
    async def orders(request, customer):
        return JSONResponse(db.all(ORDER + " ORDER BY created_at DESC", customer))

    @auth.required
    async def get_order(request, customer):
        found = order(customer, request.path_params["number"])
        return JSONResponse(found) if found else error(404, "Order not found")

    @auth.required
    async def cancel(request, customer):
        number = request.path_params["number"]
        sql = "UPDATE orders SET status = 'cancelled' WHERE number = ?"
        return update_processing(customer, number, "cancelled", sql, (number,))

    @auth.required
    async def change_address(request, customer):
        number = request.path_params["number"]
        address = str((await body(request)).get("address", "")).strip()
        if not 5 <= len(address) <= 200:
            return error(422, "address must be 5 to 200 characters")
        sql = "UPDATE orders SET address = ? WHERE number = ?"
        return update_processing(customer, number, "redirected", sql, (address, number))

    @auth.required
    async def refund(request, customer):
        current = order(customer, request.path_params["number"])
        if current is None:
            return error(404, "Order not found")
        if current["status"] != "delivered":
            return error(409, "Only a delivered order can be refunded")
        data = await body(request)
        amount, reason = data.get("amount"), str(data.get("reason", "")).strip()
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
            return error(422, "amount must be a positive number")
        if not reason:
            return error(422, "reason is required")
        with db.transaction() as tx:
            already = tx.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM refunds WHERE order_number = ?",
                (current["number"],),
            ).fetchone()[0]
            if already + amount > current["total"]:
                return error(409, "The amount is more than what is left to refund")
            tx.execute(
                "INSERT INTO refunds (order_number, amount, reason, created_at)"
                " VALUES (?, ?, ?, ?)",
                (current["number"], amount, reason[:300], datetime.now(UTC).isoformat()),
            )
        return JSONResponse(order(customer, current["number"]))

    return Starlette(
        routes=[
            *portal_routes(HERE / "portal.html", db, "shopx"),
            Route("/me", me),
            Route("/orders", orders),
            Route("/orders/{number}", get_order),
            Route("/orders/{number}/cancel", cancel, methods=["POST"]),
            Route("/orders/{number}/address", change_address, methods=["PATCH"]),
            Route("/orders/{number}/refund", refund, methods=["POST"]),
        ]
    )
