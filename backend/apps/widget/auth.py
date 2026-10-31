"""Who the widget's customer is: a token the product's own backend signed, never the browser.

The product signs `<tenant>.<customer_id>.<expires_unix>.<hmac_sha256_hex>` with its widget secret
(WIDGET_SECRETS[tenant]), the same format as execution/identity.py, and the widget sends it as
`Authorization: Bearer <token>`. Each (tenant, customer) gets a shadow Django user, so the chat
services and the orchestrator work for it unchanged.
"""

import hashlib
import hmac
import re
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
PREFIX = "widget"


def verify(token: str) -> tuple[str, str]:
    """Return (tenant, customer) the token was signed for, or raise AuthenticationFailed."""
    parts = token.split(".")
    if len(parts) != 4:
        raise AuthenticationFailed("Malformed token.")
    tenant, customer, expires, signature = parts
    if not (ID.fullmatch(tenant) and ID.fullmatch(customer) and expires.isdigit()):
        raise AuthenticationFailed("Malformed token.")
    secret = settings.WIDGET_SECRETS.get(tenant)
    if not secret:
        raise AuthenticationFailed("Unknown product.")
    payload = f"{tenant}.{customer}.{expires}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise AuthenticationFailed("Bad signature.")
    if int(expires) < time.time():
        raise AuthenticationFailed("Token expired.")
    return tenant, customer


def identity(user) -> tuple[str, str] | None:
    """(tenant, customer) of a widget customer's shadow user; None for anyone else."""
    parts = user.get_username().split(":")
    return (parts[1], parts[2]) if len(parts) == 3 and parts[0] == PREFIX else None


class WidgetTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if len(header) != 2 or header[0].lower() != b"bearer":
            return None
        tenant, customer = verify(header[1].decode("ascii", errors="replace"))
        # ":" never passes Django's username validator, so no normal account can take this name.
        user, created = get_user_model().objects.get_or_create(
            username=f"{PREFIX}:{tenant}:{customer}"
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user, None

    def authenticate_header(self, request):
        return "Bearer"  # makes DRF answer 401, which tells the widget to refresh its token
