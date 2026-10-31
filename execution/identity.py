"""Whose session this is: product (tenant) and customer, from a signed token, never from the model.

Our backend signs a token for the logged-in customer and sends it as `X-Customer-Token` on every
request to the execution server. The model never sees it, and no tool takes a product or a
customer as an argument. Format: `<tenant>.<customer_id>.<expires_unix>.<hmac_sha256_hex>`,
where tenant and customer_id are the product's own ids (letters, digits, `_`, `-`).

Mint one by hand:  EXECUTION_SECRET=... python -m execution.mint shopx s-201
"""

import hashlib
import hmac
import os
import re
import time

TOKEN_HEADER = "X-Customer-Token"
ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


class IdentityError(Exception):
    pass


def _signature(payload: str) -> str:
    secret = os.environ.get("EXECUTION_SECRET")
    if not secret:
        raise IdentityError("EXECUTION_SECRET is not set")
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def sign(tenant: str, customer: str, ttl: int = 3600) -> str:
    if not (ID.fullmatch(tenant) and ID.fullmatch(customer)):
        raise ValueError("tenant and customer must be plain ids")
    payload = f"{tenant}.{customer}.{int(time.time()) + ttl}"
    return f"{payload}.{_signature(payload)}"


def verify(token: str | None) -> tuple[str, str]:
    """Return (tenant, customer) the token was signed for, or raise IdentityError."""
    parts = (token or "").split(".")
    if len(parts) != 4:
        raise IdentityError("malformed token")
    tenant, customer, expires, signature = parts
    if not (ID.fullmatch(tenant) and ID.fullmatch(customer) and expires.isdigit()):
        raise IdentityError("malformed token")
    if not hmac.compare_digest(signature, _signature(f"{tenant}.{customer}.{expires}")):
        raise IdentityError("bad signature")
    if int(expires) < time.time():
        raise IdentityError("token expired")
    return tenant, customer
