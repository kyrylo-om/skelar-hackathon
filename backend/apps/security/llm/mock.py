"""Deterministic stand-in for the model, for tests and for demos without a key.

`respond(role, system, user)` returns the raw JSON text a real model would. It reads the
blocks the router puts into the user message (<customer_message> and the CONTEXT/PLAN
JSON) and applies simple heuristics. It is not a model; real accuracy needs a real key.
"""

import json
import re

ATTACK_MARKERS = ("ignore", "ігнор", "system prompt", "системн", "jailbreak", "забудь")
ANGRY = re.compile(r"!{2,}|жах|обурл|неприпустим|ненавиджу|безлад")
INTENTS = [
    ("legal_threat", r"\bсуд\b|подам до суду|lawsuit|chargeback"),
    ("human_request", r"людин|оператор|менеджер|human|agent"),
    ("refund", r"поверн|рефанд|refund"),
    ("cancel_renewal", r"скас|cancel|не хочу, щоб списува"),
    ("activation_issue", r"оплат\w+.*(не|досі)|не активув|paid.*not|not active"),
    ("subscription_status", r"який у мене тариф|статус підписк|мій тариф"),
    ("info_question", r"скільки місця|які тарифи|how much"),
]


def _block(user: str, tag: str) -> str:
    match = re.search(rf"<{tag}>\n(.*?)\n</{tag}>", user, re.S)
    return match.group(1) if match else ""


def _json_after(user: str, label: str):
    match = re.search(rf"^{label}:\n(.*?)(?:\n\n|\Z)", user, re.S | re.M)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except ValueError:
        return {}


def _guard(user: str) -> dict:
    text = _block(user, "customer_message").casefold()
    return {"attack": any(marker in text for marker in ATTACK_MARKERS), "why": "mock heuristic"}


def _triage(user: str) -> dict:
    text = _block(user, "customer_message")
    lowered = text.casefold()
    intent = next((name for name, pattern in INTENTS if re.search(pattern, lowered)), "unclear")
    angry = bool(ANGRY.search(lowered)) or (len(text) > 8 and text.isupper())
    cyrillic = bool(re.search(r"[іїєґа-яА-Я]", text))
    return {
        "language": "uk" if cyrillic else "en",
        "intent": intent,
        "confidence": 0.3 if intent == "unclear" else 0.8,
        "sentiment": "angry" if angry else "neutral",
        "priority": "high" if angry or intent == "legal_threat" else "normal",
    }


def _actor(user: str) -> dict:
    context = _json_after(user, "CONTEXT")
    intent = (context.get("triage") or {}).get("intent", "unclear")
    if intent in ("unclear", "smalltalk", "out_of_scope"):
        return {"actions": [], "needs_clarification": "Підкажіть, будь ласка, що саме потрібно?"}
    action = {"name": "escalate_to_human", "params": {"reason": "mock"}, "reasoning": "mock"}
    return {"intent": intent, "actions": [action], "needs_clarification": None}


def _critic(user: str) -> dict:
    message = _block(user, "customer_message")
    plan = _json_after(user, "PLAN")
    context = _json_after(user, "CONTEXT")
    asked = [float(n) for n in re.findall(r"\d+(?:[.,]\d+)?", message.replace(",", "."))]
    for action in plan.get("actions", []):
        params = action.get("params", {})
        amount = params.get("amount")
        if amount is not None and (not asked or amount > max(asked)):
            return {"verdict": "reject", "reason": "Сума в плані більша за ту, що просив клієнт"}
        current = context.get("current_order")
        if current and params.get("order") not in (None, current):
            return {"verdict": "reject", "reason": "План стосується іншого замовлення"}
    return {"verdict": "approve", "reason": "План відповідає запиту"}


def _responder(user: str) -> dict:
    context = _json_after(user, "CONTEXT")
    texts = {
        "execute": "Готово: дію виконано.",
        "review": "Передав ваш запит спеціалісту, відповімо в цьому чаті.",
        "block": "Не можу виконати цей запит. Опишіть, будь ласка, вашу ситуацію.",
        "clarify": context.get("clarification") or "Підкажіть, будь ласка, що саме потрібно?",
    }
    return {"text": texts.get(context.get("decision"), texts["review"])}


HANDLERS = {
    "guard": _guard,
    "triage": _triage,
    "actor": _actor,
    "critic": _critic,
    "responder": _responder,
}


def respond(role: str, system: str, user: str) -> str:
    return json.dumps(HANDLERS[role](user), ensure_ascii=False)
