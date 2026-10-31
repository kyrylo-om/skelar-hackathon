"""Critic: an independent LLM review of the plan against what the customer actually asked."""

from . import router
from .contracts import NEEDS_HUMAN, CriticResult


def _without_reasoning(plan: dict) -> dict:
    """The Actor's own justification stays hidden so it cannot talk the Critic round."""
    actions = [
        {key: value for key, value in action.items() if key != "reasoning"}
        for action in plan.get("actions") or []
        if isinstance(action, dict)
    ]
    return {**plan, "actions": actions}


def review_plan(message: str, plan: dict, ctx: dict | None = None) -> CriticResult:
    ctx = ctx or {}
    context = {
        # The Critic must see the same facts the plan was built from, or it cannot check them.
        "facts": ctx.get("facts"),
        # The server's own view of this customer's payments and subscriptions.
        "payments": ctx.get("payments"),
        "subscriptions": ctx.get("subscriptions"),
        "current_order": ctx.get("current_order"),
        "pending_action": ctx.get("pending_action"),
        "retention_offered": ctx.get("retention_offered", False),
        "history": ctx.get("history"),
    }
    result = router.route(
        "critic",
        {"plan": _without_reasoning(plan), "context": context, "customer_message": message},
    )
    if result.get("_fallback"):
        return CriticResult(NEEDS_HUMAN, "Рецензент не дав валідної відповіді")
    return CriticResult(result["verdict"], result["reason"])
