"""Append-only audit trail: one JSON line per tool call and per proposal decision."""

import json
import os
from datetime import UTC, datetime

OK = "ok"
DENIED = "denied"
FAILED = "failed"


def write(event: str, tenant: str | None, customer: str | None, outcome: str, **details) -> None:
    entry = {
        "at": datetime.now(UTC).isoformat(),
        "event": event,
        "tenant": tenant,
        "customer": customer,
        "outcome": outcome,
        **details,
    }
    path = os.environ.get("EXECUTION_AUDIT_LOG", "audit.jsonl")
    with open(path, "a", encoding="utf-8") as log:
        log.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
