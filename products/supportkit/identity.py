"""Who the customer is. Comes from a signed token in a request header, never from a tool argument.

The orchestrator signs a token for the logged-in customer and sends it as `X-Customer-Token`
on every request to an MCP server. The model never sees it and cannot choose whose data a
tool touches. Token format: `<customer_id>.<expires_unix>.<hmac_sha256_hex>`.

Mint one by hand:  SUPPORTKIT_SECRET=... python -m supportkit 7
"""

import hashlib
import hmac
import os
import time


class IdentityError(Exception):
    pass


def _secret() -> bytes:
    secret = os.environ.get("SUPPORTKIT_SECRET")
    if not secret:
        raise IdentityError("SUPPORTKIT_SECRET is not set")
    return secret.encode()


def _signature(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def sign(customer_id: int, ttl: int = 3600) -> str:
    payload = f"{customer_id}.{int(time.time()) + ttl}"
    return f"{payload}.{_signature(payload)}"


def verify(token: str | None) -> int:
    """Return the customer id the token was signed for, or raise IdentityError."""
    parts = (token or "").split(".")
    if len(parts) != 3 or not (parts[0].isdigit() and parts[1].isdigit()):
        raise IdentityError("malformed token")
    customer, expires, signature = parts
    if not hmac.compare_digest(signature, _signature(f"{customer}.{expires}")):
        raise IdentityError("bad signature")
    if int(expires) < time.time():
        raise IdentityError("token expired")
    return int(customer)
