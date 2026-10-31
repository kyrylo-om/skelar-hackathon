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
    """Plans from the CONTEXT the orchestrator supplies: triage, facts and allowed actions."""
    context = _json_after(user, "CONTEXT")
    intent = (context.get("triage") or {}).get("intent", "unclear")
    allowed = {a["name"] for a in context.get("allowed_actions", [])}
    facts = context.get("facts") or {}

    def plan(name, params=None, why="mock"):
        if name not in allowed:
            name, params = "escalate_to_human", {"reason": "mock: no allowed action fits"}
        action = {"name": name, "params": params or {}, "reasoning": why}
        return {"intent": intent, "actions": [action], "needs_clarification": None}

    def ask(question):
        return {"intent": intent, "actions": [], "needs_clarification": question}

    if intent in ("unclear", "smalltalk", "out_of_scope"):
        return ask("Підкажіть, будь ласка, що саме потрібно: проблема з оплатою чи з підпискою?")
    if intent == "activation_issue":
        pending = [
            p
            for p in facts.get("payments", [])
            if p.get("status") == "successful" and not p.get("applied")
        ]
        if len(pending) == 1:
            return plan(
                "sync_subscription", {"payment_id": pending[0]["id"]}, "one unapplied payment"
            )
        if len(pending) > 1:
            return ask("Бачу кілька оплат. Яка саме з них не активувала тариф?")
        return plan("escalate_to_human", {"reason": "no unapplied payment found"})
    if intent == "subscription_status":
        return plan("get_subscription")
    if intent == "cancel_renewal":
        return plan("cancel_auto_renewal")
    return plan("escalate_to_human", {"reason": f"mock: {intent}"})


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
    """Without a real model, the draft the orchestrator supplies is the reply."""
    context = _json_after(user, "CONTEXT")
    if context.get("draft"):
        return {"text": context["draft"]}
    texts = {
        "execute": "Готово: дію виконано.",
        "review": "Передав ваш запит спеціалісту, відповімо в цьому чаті.",
        "block": "Не можу виконати цей запит. Опишіть, будь ласка, вашу ситуацію.",
        "clarify": context.get("clarification") or "Підкажіть, будь ласка, що саме потрібно?",
    }
    return {"text": texts.get(context.get("decision"), texts["review"])}


def _agent(user: str) -> dict:
    context = _json_after(user, "CONTEXT")
    observations = context.get("observations") or []
    endpoints = context.get("available_endpoints") or []
    if not observations:
        for ep in endpoints:
            if ep.get("kind") == "read" or ep.get("method") == "GET":
                path = ep.get("path", "")
                if "{" not in path:
                    return {
                        "type": "call",
                        "endpoint": ep.get("id"),
                        "params": {},
                        "why": "Read initial facts",
                    }
    return {"type": "final", "reply": "Інформацію перевірено."}


HANDLERS = {
    "guard": _guard,
    "triage": _triage,
    "actor": _actor,
    "critic": _critic,
    "responder": _responder,
    "agent": _agent,
}


def respond(role: str, system: str, user: str) -> str:
    return json.dumps(HANDLERS[role](user), ensure_ascii=False)
