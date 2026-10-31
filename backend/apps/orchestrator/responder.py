"""Reply text for the customer, built only from what really happened.

Templates come from the manifest. Optionally the Responder LLM rewrites a template more naturally,
but its text is used only if every number and date in it is already in the template and it contains
nothing from the forbidden list; otherwise the template stands.
"""

import re

from django.conf import settings

from apps.security import router

from .gateway import AWAITING, DONE, FAILED, ActionOutcome
from .manifest import Manifest

FORBIDDEN = (
    "guard",
    "critic",
    "policy",
    "правил",
    "ліміт",
    "фільтр",
    "prompt",
    "cvv",
    "пароль",
    "номер картки",
)
MAX_LENGTH = 600


def _facts_for_template(outcome: ActionOutcome, facts: dict) -> dict:
    subscription = facts.get("subscription") or {}
    merged = {
        "plan": subscription.get("plan", ""),
        "period_end": subscription.get("period_end", ""),
        "auto_renew": "увімкнено" if subscription.get("auto_renew") else "вимкнено",
        "payments": "; ".join(
            f"{p['plan']} {p['amount']:g} {p['currency']} ({p['status']})"
            for p in facts.get("payments", [])[:3]
        ),
    }
    merged.update(outcome.facts if outcome.action != "get_payments" else {})
    return merged


def action_reply(outcome: ActionOutcome, facts: dict, manifest: Manifest) -> str:
    """The deterministic text for one action's result."""
    if outcome.status == FAILED:
        return manifest.responses["failed"]
    templates = manifest.responses
    if outcome.action == "get_subscription" and not facts.get("subscription"):
        return templates["get_subscription.none"]
    if outcome.action == "get_payments" and not facts.get("payments"):
        return templates["get_payments.none"]
    if outcome.facts.get("already"):
        key = f"{outcome.action}.already"
    else:
        key = f"{outcome.action}.{'awaiting' if outcome.status == AWAITING else 'done'}"
    template = templates.get(key)
    if template is None:
        return templates["failed"]
    return template.format(**_facts_for_template(outcome, facts))


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,:\-/]\d+)*", text))


def polish_is_safe(original: str, polished: str) -> bool:
    lowered = polished.lower()
    if not polished.strip() or len(polished) > MAX_LENGTH:
        return False
    if any(word in lowered for word in FORBIDDEN):
        return False
    return _numbers(polished) <= _numbers(original)


def polish(text: str, decision: str, language: str) -> str:
    """Optionally let the Responder LLM phrase `text` more naturally; fall back to `text`."""
    if not settings.ORCHESTRATOR_LLM_RESPONDER:
        return text
    answer = router.route(
        "responder",
        {
            "context": {
                "decision": decision,
                "language": language,
                "tone": "friendly",
                "draft": text,
            }
        },
    )
    if answer.get("_fallback"):
        return text
    return answer["text"] if polish_is_safe(text, answer["text"]) else text


def outcome_reply(outcomes: list[ActionOutcome], facts: dict, manifest: Manifest) -> str:
    done = [o for o in outcomes if o.status in (DONE, AWAITING, FAILED)]
    return " ".join(action_reply(o, facts, manifest) for o in done) or manifest.responses["failed"]
