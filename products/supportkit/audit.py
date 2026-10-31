"""Append-only audit trail: one JSON line per tool call, whatever the outcome."""

import json
import os
from datetime import UTC, datetime

# ok | pending | denied | error
OK = "ok"
PENDING = "pending"
DENIED = "denied"
ERROR = "error"


def write(
    server: str, tool: str, customer_id: int | None, params: dict, outcome: str, detail: str = ""
) -> None:
    entry = {
        "at": datetime.now(UTC).isoformat(),
        "server": server,
        "tool": tool,
        "customer_id": customer_id,
        "params": params,
        "outcome": outcome,
        "detail": detail,
    }
    path = os.environ.get("SUPPORTKIT_AUDIT_LOG", "audit.jsonl")
    with open(path, "a", encoding="utf-8") as log:
        log.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
