"""Gate: decides what may happen next with a customer's message and the Actor's plan.

    from apps.security.gate import gate

    result = gate(customer_id, message, plan, ctx)
    # customer_id: from the session, never from the message text.
    # plan: {"intent": "...", "actions": [{"name": "issue_refund",
    #        "params": {"order": "1042", "amount": 30}, "reasoning": "..."}],
    #        "needs_clarification": None}
    # ctx: facts about this customer, see policy.py.

    result.decision:
        execute  every action passed; run them now
        review   a human must approve first (queue it; after approval Policy runs again)
        block    refused (attack or denied action); tell the customer no, do not retry
        clarify  the plan was rejected or incomplete; ask the Actor for a new plan or the customer
    result.trace is the list of trace steps for the frontend; result.reason is a short explanation.

The orchestrator needs the Actor to see the masked text before it plans, so the same logic is also
exposed in two halves: `screen_input` (Guard) and `gate_plan` (Critic, then Policy per action).
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
    GuardResult,
    trace_step,
)


def screen_input(customer_id: int, message: str) -> tuple[GuardResult, dict]:
    """Guard step: returns its result and the trace line for it."""
    checked = guard.check_input(message, customer_id)
    step = trace_step("guard", checked.verdict, checked.reason or "Ознак атаки немає")
    return checked, step


def gate_plan(
    customer_id: int,
    masked_text: str,
    plan: dict,
    ctx: dict | None = None,
    trace: list[dict] | None = None,
    record: bool = True,
) -> GateResult:
    """Critic and Policy on a plan. `record=False` leaves the action log to the caller, which
    should record only actions that really ran."""
    ctx = ctx or {}
    trace = list(trace or [])

    if plan.get("needs_clarification"):
        return GateResult(CLARIFY, trace, str(plan["needs_clarification"]))
    actions = plan.get("actions") or []
    if not actions:
        return GateResult(CLARIFY, trace, "План не містить дій")

    reviewed = critic.review_plan(masked_text, plan, ctx)
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

    if record:
        for action in actions:
            policy.record(customer_id, action["name"], action.get("params") or {})
    return GateResult(EXECUTE, trace, "Усі перевірки пройдено")


def gate(customer_id: int, message: str, plan: dict, ctx: dict | None = None) -> GateResult:
    checked, step = screen_input(customer_id, message)
    if checked.verdict == BLOCK:
        return GateResult(BLOCK, [step], checked.reason)
    return gate_plan(customer_id, checked.masked_text, plan, ctx, [step])
