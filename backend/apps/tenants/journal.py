"""The ApiCall journal: every call the agent side makes to a product, with secrets masked."""

import time
from contextlib import contextmanager

from .models import ApiCall
from .sanitize import sanitize


def record(
    *,
    tenant: str,
    kind: str,
    method: str,
    path: str,
    status="",
    duration_ms: int = 0,
    endpoint_id: str = "",
    request=None,
    response=None,
    chat=None,
    customer: str = "",
    initiator: str = "agent",
) -> ApiCall:
    return ApiCall.objects.create(
        tenant=tenant,
        kind=kind,
        method=method,
        path=path[:500],
        status=str(status)[:24],
        duration_ms=duration_ms,
        endpoint_id=endpoint_id,
        request=sanitize(request or {}),
        response=sanitize(response or {}),
        chat=chat,
        customer=customer,
        initiator=initiator,
    )


@contextmanager
def timed():
    """Yields a function returning milliseconds since the block started."""
    started = time.monotonic()
    yield lambda: int((time.monotonic() - started) * 1000)
