"""The way out to a connected product: our execution server (MCP), nothing else.

This module only loads the real client lazily; everything else in apps/tenants talks to the
small interface below, so tests can supply a stand-in that fronts the mock products.

    context(token) -> str                     the product's own text (what it is, rules, API)
    read(token, path) -> {"http_status", "data"}
    propose(token, method, path, summary, body) -> {"proposal_id", "status"}   (NOT run)
    proposal(id) / execute(id) / reject(id)    what only our backend may do

The customer token is signed here from the session's customer (never from model output) and is
passed to the client; it is never placed in a prompt or a log.
"""

import sys

from django.conf import settings


class TenantUnavailable(Exception):
    """The product or the execution server cannot be used right now: fail closed."""


def _execution():
    path = str(settings.EXECUTION_REPO_PATH)
    if path not in sys.path:
        sys.path.append(path)
    try:
        from execution import client, identity
    except ImportError as exc:  # the MCP package or the execution folder is missing
        raise TenantUnavailable(f"execution server client is not available: {exc}") from exc
    return client, identity


def make_token(tenant: str, external_id: str) -> str:
    return _execution()[1].sign(tenant, external_id)


def get_client():
    client, _ = _execution()
    if not settings.EXECUTION_SERVICE_KEY:
        raise TenantUnavailable("EXECUTION_SERVICE_KEY is not set")
    return client.ExecutionClient(settings.EXECUTION_URL, settings.EXECUTION_SERVICE_KEY)
