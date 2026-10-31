"""Agent reasoning loop: read the connected product, gather facts, then decide or write.

The model only reads during the loop. If it proposes a write, the loop stops at once and hands
the proposal to Gate (Critic + Policy). The loop itself never performs a write.
"""

from dataclasses import dataclass, field

from django.conf import settings

from apps.security import router
from apps.security.contracts import trace_step

from .client import TenantUnavailable
from .endpoints import EndpointError
from .sanitize import sanitize


@dataclass
class AgentResult:
    kind: str  # "final" | "ask_user" | "escalate" | "write"
    reply: str = ""
    question: str = ""
    reason: str = ""
    write: dict | None = (
        None  # {"endpoint": Endpoint, "path_params": dict, "body": dict, "why": str}
    )
    trace: list[dict] = field(default_factory=list)


def run(session, masked_text: str, history: list | None = None) -> AgentResult:
    history = list(history or [])
    trace = []
    max_steps = getattr(settings, "TENANT_AGENT_MAX_STEPS", 6)

    available_endpoints = [
        {
            "id": ep.id,
            "method": ep.method,
            "path": ep.path,
            "kind": ep.kind,
            "description": ep.description,
            "body_fields": list(ep.body_example.keys()),
        }
        for ep in session.tenant.endpoints.values()
    ]
    business_context = session.tenant.context[:6000]

    for step_num in range(1, max_steps + 1):
        context = {
            "business_context": business_context,
            "available_endpoints": available_endpoints,
            "observations": list(session.observations),
            "history": history,
            "step": step_num,
        }
        raw = router.route("agent", {"context": context, "customer_message": masked_text})
        if raw.get("_fallback"):
            return AgentResult(
                kind="escalate",
                reason=raw.get("reason", "agent unavailable"),
                trace=trace,
            )

        decision_type = raw.get("type")
        if decision_type == "call":
            endpoint_id = raw.get("endpoint")
            endpoint = session.tenant.endpoint(endpoint_id) if endpoint_id else None
            if endpoint is None:
                trace.append(trace_step("actor", "reject", f"unknown endpoint: {endpoint_id}"))
                session.observations.append({"error": f"Endpoint {endpoint_id} does not exist"})
                continue

            if endpoint.kind == "read":
                params = raw.get("params") or {}
                try:
                    answer = session.read(endpoint, params, initiator="agent")
                    data = sanitize(answer.get("data"))
                    session.observations.append(
                        {"endpoint": endpoint.id, "status": answer.get("http_status"), "data": data}
                    )
                    trace.append(trace_step("actor", "info", f"{endpoint.method} {endpoint.path}"))
                except (TenantUnavailable, EndpointError) as exc:
                    session.observations.append({"endpoint": endpoint.id, "error": str(exc)})
                    trace.append(trace_step("actor", "reject", f"{endpoint.id}: {exc}"))
                continue

            # write endpoint: stop loop, Gate must review first
            path_params = raw.get("params") or {}
            body = raw.get("body") or {}
            why = raw.get("why", "")
            return AgentResult(
                kind="write",
                write={
                    "endpoint": endpoint,
                    "path_params": path_params,
                    "body": body,
                    "why": why,
                },
                trace=trace,
            )

        if decision_type == "ask_user":
            return AgentResult(
                kind="ask_user",
                question=raw.get("question", ""),
                trace=trace,
            )

        if decision_type == "escalate":
            return AgentResult(
                kind="escalate",
                reason=raw.get("reason", "agent requested escalation"),
                trace=trace,
            )

        if decision_type == "final":
            return AgentResult(
                kind="final",
                reply=raw.get("reply", ""),
                trace=trace,
            )

        # Unrecognized decision structure fails closed
        return AgentResult(kind="escalate", reason="invalid agent decision", trace=trace)

    return AgentResult(kind="escalate", reason="loop limit", trace=trace)
