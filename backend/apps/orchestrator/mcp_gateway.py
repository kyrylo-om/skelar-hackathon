"""The door to an external product: the execution server (`execution/` at the repository root).

`McpGateway` has the interface of `DevDomainGateway` (`load_facts`, `turn`, `run`), so the
pipeline does not care which product it drives. It talks to the server as the session's customer
over MCP (read, propose) and, as our backend, over its HTTP endpoints (execute). Every change is
first proposed and stored there, and runs only when this code executes it: right away once Gate
said "execute", or when the customer presses confirm for `confirm: customer` actions.

The customer is identified by a short-lived token signed here for the session's user. The product
sees its own customer id from EXECUTION_CUSTOMERS, never anything the model wrote.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from contextlib import contextmanager
from datetime import timedelta

import httpx2
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from rest_framework.exceptions import NotFound

from apps.core.errors import Conflict
from apps.review.models import Chat

from .gateway import AWAITING, DONE, FAILED, ActionOutcome
from .manifest import get_manifest
from .models import ProductConfirmation

logger = logging.getLogger("apps.orchestrator")

TOKEN_HEADER = "X-Customer-Token"
TOKEN_TTL = 300
CONFIRM_WINDOW = timedelta(minutes=10)
MAX_PAYMENTS = 10
READ_ONLY = ("get_subscription", "get_payments")
# How the CloudBox API does each state-changing action: (method, path, body template). Moves into
# the manifest's `executor` (docs/agents/08_MANIFEST.md) once the manifest leaves Python.
CALLS = {
    "sync_subscription": ("POST", "/subscription/sync", {"payment_id": "{payment_id}"}),
    "cancel_auto_renewal": ("POST", "/subscription/auto-renewal/off", {}),
}
DESCRIPTIONS = {
    "cancel_auto_renewal": (
        "Вимкнути автоподовження. Доступ збережеться до кінця оплаченого періоду."
    ),
}


class ProductUnavailable(Exception):
    """The execution server or the product did not give a usable answer."""


class ExecutionClient:
    """Synchronous client for the execution server; the same contract as execution/client.py."""

    def __init__(self):
        self.url = settings.EXECUTION_URL.rstrip("/")

    def read(self, token: str, path: str) -> dict:
        return self._tool(token, "read", {"path": path})

    def propose(self, token: str, method: str, path: str, summary: str, body: dict) -> dict:
        args = {"method": method, "path": path, "summary": summary, "body": body}
        return self._tool(token, "propose_call", args)

    def execute(self, proposal_id: str) -> dict:
        return self._http("POST", f"/proposals/{proposal_id}/execute")

    def _tool(self, token: str, name: str, args: dict) -> dict:
        async def call():
            async with httpx2.AsyncClient(headers={TOKEN_HEADER: token}, timeout=15) as http:
                transport = streamable_http_client(f"{self.url}/mcp", http_client=http)
                async with Client(transport) as mcp:
                    return await mcp.call_tool(name, args)

        try:
            result = asyncio.run(call())
        except Exception as exc:  # any transport or protocol failure means "unavailable"
            logger.warning("execution server call %s failed: %r", name, exc)
            raise ProductUnavailable("execution server is not reachable") from exc
        text = result.content[0].text if result.content else ""
        if result.is_error:
            raise ProductUnavailable(text)
        return result.structured_content or json.loads(text)

    def _http(self, method: str, path: str) -> dict:
        headers = {"Authorization": f"Bearer {settings.EXECUTION_SERVICE_KEY}"}
        try:
            response = httpx2.request(method, self.url + path, headers=headers, timeout=15)
        except httpx2.HTTPError as exc:
            raise ProductUnavailable("execution server is not reachable") from exc
        if response.status_code >= 400:
            raise ProductUnavailable(response.json().get("detail", response.text))
        return response.json()


def _date(value: str | None) -> str | None:
    return value[:10] if value else None


def _facts(subscription: dict | None, payments: list) -> dict:
    """CloudBox API answers in the shape Actor, Critic and Policy read (see facts.load_facts)."""
    return {
        "subscription": None
        if not subscription
        else {
            "id": subscription["id"],
            "plan": subscription["plan"],
            "status": subscription["status"],
            "auto_renew": bool(subscription["auto_renew"]),
            "period_end": _date(subscription["period_end"]),
        },
        "payments": [
            {
                "id": p["id"],
                "plan": p["plan"],
                "amount": float(p["amount"]),
                "currency": "UAH",
                "status": p["status"],
                "applied": p["applied_at"] is not None,
                "period_end": None,
            }
            for p in payments[:MAX_PAYMENTS]
        ],
    }


class McpGateway:
    def __init__(self, user, client: ExecutionClient | None = None):
        self.user = user
        self.client = client or ExecutionClient()
        self.customer = settings.EXECUTION_CUSTOMERS.get(user.get_username())

    def token(self) -> str:
        if not self.customer:
            raise ProductUnavailable("this account is not connected to the product")
        if not settings.EXECUTION_SECRET:
            raise ProductUnavailable("EXECUTION_SECRET is not set")
        payload = f"{settings.EXECUTION_TENANT}.{self.customer}.{int(time.time()) + TOKEN_TTL}"
        key = settings.EXECUTION_SECRET.encode()
        return f"{payload}.{hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()}"

    def _read(self, token: str, path: str):
        answer = self.client.read(token, path)
        if answer["http_status"] >= 400:
            raise ProductUnavailable(f"GET {path} answered {answer['http_status']}")
        return answer["data"]

    def load_facts(self) -> dict:
        token = self.token()
        return _facts(self._read(token, "/subscription"), self._read(token, "/payments"))

    def hand_off(self) -> int:
        """The chat moved to a human: no confirm button the AI produced may run any more."""
        return ProductConfirmation.objects.filter(
            customer=self.user, status=ProductConfirmation.Status.AWAITING
        ).update(status=ProductConfirmation.Status.REJECTED)

    @contextmanager
    def turn(self, label: str = ""):
        """No lease is needed: a proposal runs at most once on the server."""
        yield self.token()

    def run(self, token, action: str, params: dict, facts: dict, reason: str = "") -> ActionOutcome:
        if action in READ_ONLY:
            return ActionOutcome(action, DONE, facts=facts)
        if action not in CALLS:
            return ActionOutcome(action, FAILED, error="Дію не підтримує підключений продукт")
        subscription = facts.get("subscription")
        if action == "cancel_auto_renewal" and subscription and not subscription["auto_renew"]:
            return ActionOutcome(action, DONE, facts={"already": True})  # nothing to change

        spec = get_manifest().actions[action]
        method, path, body = CALLS[action]
        summary = f"{spec.description}. {reason}".strip(" .")[:300]
        try:
            proposal = self.client.propose(
                token,
                method,
                path.format(**params),
                summary,
                {key: value.format(**params) for key, value in body.items()},
            )
        except ProductUnavailable as exc:
            return ActionOutcome(action, FAILED, error=str(exc))

        if spec.confirm == "customer":
            pending = ProductConfirmation.objects.create(
                customer=self.user,
                action=action,
                params=params,
                proposal_id=proposal["proposal_id"],
                expires_at=timezone.now() + CONFIRM_WINDOW,
            )
            return ActionOutcome(action, AWAITING, action_id=str(pending.pk))
        return self.execute(action, proposal["proposal_id"])

    def execute(self, action: str, proposal_id: str) -> ActionOutcome:
        try:
            answer = self.client.execute(proposal_id)
        except ProductUnavailable as exc:
            return ActionOutcome(action, FAILED, error=str(exc))
        body = (answer.get("result") or {}).get("body")
        if answer["status"] != "executed":
            detail = body.get("detail") if isinstance(body, dict) else None
            return ActionOutcome(action, FAILED, error=detail or "Продукт відхилив дію")
        facts = {}
        if isinstance(body, dict) and "plan" in body:
            facts = {"plan": body["plan"], "period_end": _date(body.get("period_end"))}
        return ActionOutcome(action, DONE, facts=facts, action_id=proposal_id)


def _payload(pending: ProductConfirmation) -> dict:
    return {
        "id": str(pending.pk),
        "kind": pending.action,
        "status": pending.status,
        "description": DESCRIPTIONS.get(pending.action, pending.action),
        "expires_at": pending.expires_at.isoformat(),
    }


def pending_confirmation(user) -> dict | None:
    pending = (
        ProductConfirmation.objects.filter(
            customer=user,
            status=ProductConfirmation.Status.AWAITING,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )
    return _payload(pending) if pending else None


def confirm(user, confirmation_id) -> dict:
    """The customer pressed confirm: run the stored proposal once. Only that endpoint calls this."""
    with transaction.atomic():
        pending = (
            ProductConfirmation.objects.select_for_update()
            .filter(pk=confirmation_id, customer=user)
            .first()
        )
        if pending is None:
            raise NotFound()
        if pending.status != ProductConfirmation.Status.AWAITING:
            raise Conflict("Цю дію вже підтверджено або скасовано.")
        if pending.expires_at <= timezone.now():
            raise Conflict("Час на підтвердження минув.")
        if Chat.objects.filter(customer=user, status=Chat.Status.NEEDS_REVIEW).exists():
            raise Conflict("Звернення вже передано спеціалісту.")
        pending.status = ProductConfirmation.Status.CONFIRMING
        pending.save(update_fields=["status"])

    outcome = McpGateway(user).execute(pending.action, pending.proposal_id)
    pending.status = (
        ProductConfirmation.Status.DONE
        if outcome.status == DONE
        else ProductConfirmation.Status.FAILED
    )
    pending.save(update_fields=["status"])
    if outcome.status == FAILED:
        raise Conflict(outcome.error)
    return {"action": _payload(pending), "result": outcome.facts}
