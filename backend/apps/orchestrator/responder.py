"""Reply text for the customer.

The Responder model writes every reply, from the customer's own facts and the real results of what
was done, so it can answer anything about the product (when a subscription ends, which payments
exist) in the customer's language instead of reciting fixed phrases. The manifest templates are only
the draft it is given and the fallback: if the model fails, runs out of budget, or writes something
that is not backed by the facts, the draft is sent instead.

What the model must never see: the text of a message Guard refused (the refusal is generic), and
anything outside this customer's own facts.
"""

import json
import re

from django.conf import settings

from apps.security import router

from .gateway import AWAITING, DONE, FAILED, ActionOutcome
from .manifest import Manifest

# Words that must never appear in a reply: internals, secrets, and promises nobody authorised.
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
    "гарантуємо",
    "обіцяємо",
    "компенсу",
)
MAX_LENGTH = 600
# Decisions where the customer's own words help the model answer; a refusal never gets them.
WITH_MESSAGE = ("execute", "clarify", "review")


def _facts_for_template(outcome: ActionOutcome, facts: dict) -> dict:
    subscription = facts.get("subscription") or {}
    merged = {
        "plan": subscription.get("plan", ""),
        "period_end": subscription.get("period_end"),
        "auto_renew": "увімкнено" if subscription.get("auto_renew") else "вимкнено",
        "payments": "; ".join(
            f"{p['plan']} {p['amount']:g} {p['currency']} ({p['status']})"
            for p in facts.get("payments", [])[:3]
        ),
    }
    merged.update(outcome.facts if outcome.action != "get_payments" else {})
    # One phrase that reads well in every template, with or without an end date.
    date = merged.get("period_end")
    merged["period_end"] = f"до {date}" if date else "без обмеження строку"
    return merged


def action_reply(outcome: ActionOutcome, facts: dict, manifest: Manifest) -> str:
    """The deterministic draft for one action's result."""
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


def outcome_reply(outcomes: list[ActionOutcome], facts: dict, manifest: Manifest) -> str:
    done = [o for o in outcomes if o.status in (DONE, AWAITING, FAILED)]
    return " ".join(action_reply(o, facts, manifest) for o in done) or manifest.responses["failed"]


def _digits(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


def reply_is_safe(backing: str, reply: str) -> bool:
    """A model reply is used only if it is short, clean, and every number in it is backed.

    `backing` is everything the reply may legitimately draw numbers from: the customer's facts,
    the action results and the draft. Dates may be reworded ("2026-11-29" to "29.11.2026"), but a
    digit group that appears nowhere in the backing is an invention.
    """
    lowered = reply.lower()
    if not reply.strip() or len(reply) > MAX_LENGTH:
        return False
    if any(word in lowered for word in FORBIDDEN):
        return False
    return _digits(reply) <= _digits(backing)


def compose(
    decision: str,
    draft: str,
    *,
    facts: dict,
    outcomes: list[ActionOutcome],
    history: list,
    masked_text: str,
    manifest: Manifest,
    language: str = "uk",
) -> str:
    """Let the Responder model write the reply; use the draft whenever it cannot be trusted."""
    if not settings.ORCHESTRATOR_LLM_RESPONDER:
        return draft
    results = [{"action": o.action, "status": o.status, "facts": o.facts} for o in outcomes]
    context = {
        "decision": decision,
        "brand": manifest.brand,
        "language": language,
        "tone": "friendly",
        "draft": draft,
    }
    if decision in WITH_MESSAGE:
        context |= {"facts": facts, "results": results, "history": history}
    payload = {"context": context}
    if decision in WITH_MESSAGE and masked_text:
        payload["customer_message"] = masked_text
    answer = router.route("responder", payload)
    if answer.get("_fallback"):
        return draft
    backing = draft + json.dumps(context, ensure_ascii=False, default=str)
    return answer["text"] if reply_is_safe(backing, answer["text"]) else draft
