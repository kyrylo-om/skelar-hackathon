"""Gate: the one function the dialog code calls to decide what may happen next.

from apps.security.gate import gate

result = gate(customer_id, message, plan, ctx)
# customer_id: from the session, never from the message text.
# plan: {"intent": "...", "actions": [{"name": "issue_refund",
#        "params": {"order": "1042", "amount": 30}, "reasoning": "..."}],
#        "needs_clarification": None}
# ctx: facts about this customer, see policy.py.

result.decision:
    execute  every action passed and was recorded for rate limits; run them now
    review   a human must approve first (queue it, then call policy.evaluate again on approve)
    block    refused (attack or denied action); tell the customer no, do not retry
    clarify  the plan was rejected or incomplete; ask the Actor for a new plan or ask the customer
result.trace is the list of trace steps for the frontend; result.reason is a short explanation.
"""

from . import critic, guard, policy
from .contracts import (
    APPROVE,
    BLOCK,
    CLARIFY,
    DENY,
    EXECUTE,
    NEEDS_HUMAN,
    NEEDS_REVIEW,
    REVIEW,
    GateResult,
    trace_step,
)


def gate(customer_id: int, message: str, plan: dict, ctx: dict | None = None) -> GateResult:
    ctx = ctx or {}
    trace = []

    checked = guard.check_input(message, customer_id)
    trace.append(trace_step("guard", checked.verdict, checked.reason or "Ознак атаки немає"))
    if checked.verdict == BLOCK:
        return GateResult(BLOCK, trace, checked.reason)

    if plan.get("needs_clarification"):
        return GateResult(CLARIFY, trace, str(plan["needs_clarification"]))
    actions = plan.get("actions") or []
    if not actions:
        return GateResult(CLARIFY, trace, "План не містить дій")

    reviewed = critic.review_plan(checked.masked_text, plan, ctx)
    trace.append(trace_step("critic", reviewed.verdict, reviewed.reason))
    if reviewed.verdict != APPROVE:
        decision = REVIEW if reviewed.verdict == NEEDS_HUMAN else CLARIFY
        return GateResult(decision, trace, reviewed.reason)

    results = []
    for action in actions:
        outcome = policy.evaluate(
            customer_id, str(action.get("name")), action.get("params") or {}, ctx
        )
        results.append(outcome)
        trace.append(
            trace_step("policy", outcome.decision, f"{action.get('name')}: {outcome.reason}")
        )

    denied = next((r for r in results if r.decision == DENY), None)
    if denied:
        return GateResult(BLOCK, trace, denied.reason)
    if any(r.decision == NEEDS_REVIEW for r in results):
        reason = next(r.reason for r in results if r.decision == NEEDS_REVIEW)
        return GateResult(REVIEW, trace, reason)

    for action in actions:
        policy.record(customer_id, action["name"], action.get("params") or {})
    return GateResult(EXECUTE, trace, "Усі перевірки пройдено")
