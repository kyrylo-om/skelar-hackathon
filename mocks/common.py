"""Plumbing shared by the mock products: SQLite built from context.md, auth, the demo portal.

A mock product is what a real customer of ours would hand over: an HTTP API, an API key and a
text context. The database is created from the ```sql block of that context, so the schema the
support agent reads is exactly the one the product runs on.

Two ways in:
  - the support service: `Authorization: Bearer <api key>` plus `X-Customer-Id`;
  - the product's own portal: a demo login cookie (a mock; no passwords).
"""

import re
import sqlite3
from contextlib import closing, contextmanager
from functools import wraps
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

COOKIE = "customer"


class Database:
    def __init__(self, path: Path, context: Path, seed: Path):
        self.path = Path(path)
        if not self.path.exists():
            schema = re.search(r"```sql\n(.*?)```", context.read_text(encoding="utf-8"), re.S)
            with closing(self._connect()) as db, db:
                db.executescript(schema.group(1) + seed.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def all(self, sql: str, *params) -> list[dict]:
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute(sql, params)]

    def one(self, sql: str, *params) -> dict | None:
        rows = self.all(sql, *params)
        return rows[0] if rows else None

    @contextmanager
    def transaction(self):
        """A connection whose statements commit together, or not at all if the block raises."""
        with closing(self._connect()) as db, db:
            yield db


def error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status)


async def body(request: Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class Auth:
    def __init__(self, api_key: str, db: Database):
        self.api_key = api_key
        self.db = db

    def customer(self, request: Request) -> str | None:
        if request.headers.get("authorization") == f"Bearer {self.api_key}":
            customer = request.headers.get("x-customer-id")
        else:
            customer = request.cookies.get(COOKIE)
        if customer and self.db.one("SELECT id FROM customers WHERE id = ?", customer):
            return customer
        return None

    def required(self, handler):
        """Pass the caller's customer id to `handler(request, customer)`, or answer 401."""

        @wraps(handler)
        async def endpoint(request: Request):
            customer = self.customer(request)
            if customer is None:
                return error(401, "Unknown customer")
            return await handler(request, customer)

        return endpoint


def portal_routes(page: Path, db: Database) -> list[Route]:
    """The product's own customer portal: a page, a demo login and a logout."""

    async def index(request):
        return FileResponse(page)

    async def customers(request):
        return JSONResponse(db.all("SELECT id, name FROM customers ORDER BY id"))

    async def login(request):
        customer = str((await body(request)).get("customer_id", ""))
        if not db.one("SELECT id FROM customers WHERE id = ?", customer):
            return error(404, "Unknown customer")
        response = JSONResponse({"customer_id": customer})
        response.set_cookie(COOKIE, customer, httponly=True, samesite="strict")
        return response

    async def logout(request):
        response = JSONResponse({})
        response.delete_cookie(COOKIE)
        return response

    return [
        Route("/", index),
        Route("/portal/customers", customers),
        Route("/portal/login", login, methods=["POST"]),
        Route("/portal/logout", logout, methods=["POST"]),
    ]
