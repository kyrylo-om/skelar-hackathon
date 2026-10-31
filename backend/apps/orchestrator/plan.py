"""Deterministic checks on an Actor plan, before Critic and Policy ever see it.

The model proposes; this code refuses anything that is not a plain, well-formed plan built from
the manifest's actions and from values that exist in the customer's own facts. A plan that cannot
even be inspected (wrong types anywhere) is refused with an error, never with an exception.
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


def _check_action(action, allowed: dict, facts: dict) -> tuple[list[str], bool]:
    """Problems with one action, and whether it changes state."""
    if not isinstance(action, dict):
        return ["action is not an object"], False
    name = action.get("name")
    if not isinstance(name, str):
        return ["action name must be a string"], False
    spec = allowed.get(name)
    if spec is None:
        return [f"action {name!r} is not allowed here"], False
    params = action.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return [f"{name}: params must be an object"], False
    errors = []
    if FORBIDDEN_PARAMS & set(params):
        errors.append(f"{name}: identity parameters are not allowed")
    unknown = set(params) - set(spec.params)
    if unknown:
        errors.append(f"{name}: unknown parameters {sorted(unknown)}")
    for param, source in spec.params.items():
        value = params.get(param)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{name}: {param} is required")
            continue
        values = _source_values(source, facts)
        if values is not None and value not in values:
            errors.append(f"{name}: {param} is not one of this customer's {source}")
    return errors, not spec.read_only


def _validate(plan, allowed: dict, facts: dict) -> list[str]:
    if not isinstance(plan, dict):
        return ["plan is not an object"]
    actions = plan.get("actions")
    clarification = plan.get("needs_clarification")
    if not isinstance(actions, list):
        return ["actions must be a list"]
    errors = []
    if clarification is not None and not isinstance(clarification, str):
        errors.append("needs_clarification must be a string or null")
    if actions and clarification:
        errors.append("a plan cannot both act and ask")
    priority = plan.get("priority")
    if priority is not None and (not isinstance(priority, str) or priority not in PRIORITIES):
        errors.append("invalid priority")
    risky = 0
    for action in actions:
        found, changes_state = _check_action(action, allowed, facts)
        errors.extend(found)
        risky += changes_state
    if risky > 1:
        errors.append("more than one state-changing action in a plan")
    return errors


def validate_plan(plan, allowed: dict, facts: dict) -> list[str]:
    """Return the problems found; an empty list means the plan is well formed."""
    try:
        return _validate(plan, allowed, facts)
    except Exception:  # noqa: BLE001 - whatever the model sent, the answer is "refused"
        return ["plan could not be inspected"]


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
