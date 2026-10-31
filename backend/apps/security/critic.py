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
    context = {"current_order": (ctx or {}).get("current_order")}
    result = router.route(
        "critic",
        {"plan": _without_reasoning(plan), "context": context, "customer_message": message},
    )
    if result.get("_fallback"):
        return CriticResult(NEEDS_HUMAN, "Рецензент не дав валідної відповіді")
    return CriticResult(result["verdict"], result["reason"])
