"""Confirmations: a risky tool call is parked here until the customer confirms it.

The pending action stores the exact tool and arguments, so what runs is what the customer
saw. An id is single-use, expires, and only the customer it was made for can redeem it.
"""

import os
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Pending:
    customer_id: int
    tool: str
    params: dict
    expires_at: float


class Confirmations:
    def __init__(self, ttl: int | None = None):
        self.ttl = ttl or int(os.environ.get("SUPPORTKIT_CONFIRM_TTL", "300"))
        self._pending: dict[str, Pending] = {}

    def create(self, customer_id: int, tool: str, params: dict) -> str:
        confirmation_id = secrets.token_urlsafe(16)
        self._pending[confirmation_id] = Pending(
            customer_id, tool, dict(params), time.time() + self.ttl
        )
        return confirmation_id

    def take(self, confirmation_id: str, customer_id: int) -> Pending | None:
        """Pop the pending action. Unknown, expired and someone else's ids all look the same."""
        pending = self._pending.get(confirmation_id)
        if pending is None or pending.customer_id != customer_id:
            return None
        del self._pending[confirmation_id]
        return pending if pending.expires_at >= time.time() else None
