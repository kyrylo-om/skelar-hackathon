"""The way out to a connected product: our execution server (MCP) or direct dev product gateway.

This module loads the client lazily; everything else in apps/tenants talks to the
small interface below:

    context(token) -> str                     the product's own text (what it is, rules, API)
    read(token, path) -> {"http_status", "data"}
    propose(token, method, path, summary, body) -> {"proposal_id", "status"}   (NOT run)
    proposal(id) / execute(id) / reject(id)    what only our backend may do

The customer token is signed here from the session's customer (never from model output) and is
passed to the client; it is never placed in a prompt or a log.
"""

import os
import sys
from pathlib import Path
from typing import Any

from django.conf import settings

PRODUCTS = {
    "cloudbox": {
        "url": "http://127.0.0.1:9201",
        "api_key_env": "CLOUDBOX_API_KEY",
        "default_key": "cloudbox-dev-key",
        "context_rel": "mocks/cloudbox/context.md",
    },
    "shopx": {
        "url": "http://127.0.0.1:9202",
        "api_key_env": "SHOPX_API_KEY",
        "default_key": "shopx-dev-key",
        "context_rel": "mocks/shopx/context.md",
    },
}


class TenantUnavailable(Exception):
    """The product or the execution server cannot be used right now: fail closed."""


class DevDirectExecutionClient:
    """Direct product client for dev mode and environments without external MCP daemon."""

    def __init__(self):
        self.proposals: dict[str, dict] = {}
        self._seq = 1000

    def _split_token(self, token: str) -> tuple[str, str]:
        parts = token.split(".")
        if len(parts) < 2:
            raise TenantUnavailable("malformed customer token")
        return parts[0], parts[1]

    def _product_info(self, tenant: str) -> dict:
        info = PRODUCTS.get(tenant)
        if not info:
            raise TenantUnavailable(f"unknown product tenant: {tenant}")
        return info

    def context(self, token: str) -> str:
        tenant, _ = self._split_token(token)
        info = self._product_info(tenant)
        repo_root = Path(settings.EXECUTION_REPO_PATH)
        path = repo_root / info["context_rel"]
        if not path.is_file():
            # Try from BASE_DIR parent
            path = Path(settings.BASE_DIR).parent / info["context_rel"]
        if not path.is_file():
            raise TenantUnavailable(f"context file not found for {tenant}")
        return path.read_text(encoding="utf-8")

    def read(self, token: str, path: str) -> dict:
        import httpx2

        tenant, customer = self._split_token(token)
        info = self._product_info(tenant)
        api_key = os.environ.get(info["api_key_env"], info["default_key"])
        url = info["url"].rstrip("/") + path
        headers = {"Authorization": f"Bearer {api_key}", "X-Customer-Id": customer}
        try:
            resp = httpx2.get(url, headers=headers, timeout=10)
        except Exception as exc:
            raise TenantUnavailable(f"direct product read {path} failed: {exc}") from exc
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        return {"http_status": resp.status_code, "data": data}

    def propose(
        self, token: str, method: str, path: str, summary: str, body: dict | None = None
    ) -> dict:
        tenant, customer = self._split_token(token)
        self._seq += 1
        pid = f"prop-{self._seq}"
        self.proposals[pid] = {
            "proposal_id": pid,
            "status": "pending",
            "tenant": tenant,
            "customer": customer,
            "method": method.upper(),
            "path": path,
            "summary": summary,
            "body": body or {},
            "executed": False,
        }
        return {"proposal_id": pid, "status": "pending"}

    def proposal(self, proposal_id: str) -> dict:
        return self.proposals.get(proposal_id, {})

    def execute(self, proposal_id: str) -> dict:
        import httpx2

        prop = self.proposals.get(proposal_id)
        if not prop:
            return {"status": "failed", "result": {"http_status": 404, "body": {"detail": "Not found"}}}
        if prop["executed"]:
            return {"status": "failed", "result": {"http_status": 409, "body": {"detail": "Already executed"}}}

        tenant = prop["tenant"]
        customer = prop["customer"]
        info = self._product_info(tenant)
        api_key = os.environ.get(info["api_key_env"], info["default_key"])
        url = info["url"].rstrip("/") + prop["path"]
        headers = {"Authorization": f"Bearer {api_key}", "X-Customer-Id": customer}

        try:
            resp = httpx2.request(prop["method"], url, headers=headers, json=prop["body"] or None, timeout=10)
        except Exception as exc:
            return {"status": "failed", "result": {"http_status": 500, "body": {"detail": str(exc)}}}

        prop["executed"] = True
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        status = "executed" if resp.status_code < 400 else "failed"
        return {"status": status, "result": {"http_status": resp.status_code, "body": body}}

    def reject(self, proposal_id: str) -> dict:
        prop = self.proposals.get(proposal_id)
        if prop:
            prop["status"] = "rejected"
        return {"status": "rejected"}


def _execution():
    path = str(settings.EXECUTION_REPO_PATH)
    if path not in sys.path:
        sys.path.append(path)
    os.environ.setdefault("EXECUTION_SECRET", getattr(settings, "EXECUTION_SECRET", "") or "dev-execution-secret")
    try:
        from execution import client, identity
    except ImportError as exc:
        raise TenantUnavailable(f"execution server client is not available: {exc}") from exc
    return client, identity


def make_token(tenant: str, external_id: str) -> str:
    os.environ.setdefault("EXECUTION_SECRET", getattr(settings, "EXECUTION_SECRET", "") or "dev-execution-secret")
    try:
        return _execution()[1].sign(tenant, external_id)
    except Exception:
        import hashlib
        import hmac
        import time

        secret = getattr(settings, "EXECUTION_SECRET", None) or "dev-execution-secret"
        payload = f"{tenant}.{external_id}.{int(time.time()) + 3600}"
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"


def get_client():
    mode = getattr(settings, "ORCHESTRATOR_GATEWAY", "dev")
    client_mod, _ = _execution()
    if mode == "dev" or getattr(client_mod, "Client", None) is None or not settings.EXECUTION_SERVICE_KEY:
        return DevDirectExecutionClient()
    return client_mod.ExecutionClient(settings.EXECUTION_URL, settings.EXECUTION_SERVICE_KEY)
