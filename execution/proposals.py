"""State-changing calls the model proposed. Stored exactly, run at most once, only when told to.

A proposal keeps the product, customer, method, path and body, so what runs is exactly what our
reviewers saw. It expires (EXECUTION_PROPOSAL_TTL, default one hour) and lives in memory: a
restart drops every pending proposal, which fails closed.
"""

import os
import secrets
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

PROPOSED = "proposed"
EXECUTING = "executing"
EXECUTED = "executed"
FAILED = "failed"
REJECTED = "rejected"
EXPIRED = "expired"


@dataclass
class Proposal:
    id: str
    tenant: str
    customer: str
    method: str
    path: str
    body: dict | None
    summary: str
    expires_at: float
    status: str = PROPOSED
    result: dict | None = None  # {"http_status": ..., "body": ...} once it ran

    def state(self) -> str:
        return EXPIRED if self.status == PROPOSED and self.expires_at < time.time() else self.status

    def public(self) -> dict:
        data = asdict(self) | {"status": self.state()}
        data["expires_at"] = datetime.fromtimestamp(self.expires_at, UTC).isoformat()
        return data


class Proposals:
    def __init__(self, ttl: int | None = None):
        self.ttl = ttl if ttl is not None else int(os.environ.get("EXECUTION_PROPOSAL_TTL", 3600))
        self._items: dict[str, Proposal] = {}

    def create(self, tenant, customer, method, path, body, summary) -> Proposal:
        proposal = Proposal(
            secrets.token_urlsafe(16),
            tenant,
            customer,
            method,
            path,
            body,
            summary,
            time.time() + self.ttl,
        )
        self._items[proposal.id] = proposal
        return proposal

    def get(self, proposal_id: str) -> Proposal | None:
        return self._items.get(proposal_id)

    def claim(self, proposal_id: str) -> Proposal | None:
        """Take a live proposal for execution. A second claim of the same one gets None."""
        proposal = self._items.get(proposal_id)
        if proposal is None or proposal.state() != PROPOSED:
            return None
        proposal.status = EXECUTING
        return proposal

    def reject(self, proposal_id: str) -> Proposal | None:
        proposal = self._items.get(proposal_id)
        if proposal is None or proposal.state() != PROPOSED:
            return None
        proposal.status = REJECTED
        return proposal
