"""Deterministic checks on an Actor plan, before Critic and Policy ever see it.

The model proposes; this code refuses anything that is not a plain, well-formed plan built from
the manifest's actions and from values that exist in the customer's own facts.
"""

import re

FORBIDDEN_PARAMS = {"customer_id", "tenant_id", "user_id"}
PRIORITIES = {"low", "normal", "high"}


def _source_values(source: str, facts: dict) -> set | None:
    """Allowed values for a parameter, e.g. "payments[].id". None means free text."""
    if source == "free":
        return None
    match = re.fullmatch(r"(\w+)\[\]\.(\w+)", source)
    if not match:
        return set()
    table, key = match.groups()
    return {str(row[key]) for row in facts.get(table, []) if key in row}


def validate_plan(plan, allowed: dict, facts: dict) -> list[str]:
    """Return the problems found; an empty list means the plan is well formed."""
    if not isinstance(plan, dict):
        return ["plan is not an object"]
    errors = []
    actions = plan.get("actions")
    clarification = plan.get("needs_clarification")
    if not isinstance(actions, list):
        return ["actions must be a list"]
    if clarification is not None and not isinstance(clarification, str):
        errors.append("needs_clarification must be a string or null")
    if actions and clarification:
        errors.append("a plan cannot both act and ask")
    if plan.get("priority") is not None and plan["priority"] not in PRIORITIES:
        errors.append("invalid priority")

    risky = 0
    for action in actions:
        if not isinstance(action, dict):
            errors.append("action is not an object")
            continue
        name = action.get("name")
        spec = allowed.get(name)
        if spec is None:
            errors.append(f"action {name!r} is not allowed here")
            continue
        params = action.get("params") or {}
        if not isinstance(params, dict):
            errors.append(f"{name}: params must be an object")
            continue
        if FORBIDDEN_PARAMS & set(params):
            errors.append(f"{name}: identity parameters are not allowed")
        if set(params) - set(spec.params):
            errors.append(f"{name}: unknown parameters {sorted(set(params) - set(spec.params))}")
        for param, source in spec.params.items():
            value = params.get(param)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{name}: {param} is required")
                continue
            values = _source_values(source, facts)
            if values is not None and value not in values:
                errors.append(f"{name}: {param} is not one of this customer's {source}")
        if not spec.read_only:
            risky += 1
    if risky > 1:
        errors.append("more than one state-changing action in a plan")
    return errors


def strip_identity(plan: dict) -> dict:
    """Drop fields the pipeline must never pass on, keeping only the plan's real content."""
    return {
        "intent": plan.get("intent"),
        "confidence": plan.get("confidence"),
        "priority": plan.get("priority"),
        "needs_clarification": plan.get("needs_clarification"),
        "actions": [
            {
                "name": a["name"],
                "params": a.get("params") or {},
                "reasoning": str(a.get("reasoning", ""))[:300],
            }
            for a in plan.get("actions", [])
        ],
    }
