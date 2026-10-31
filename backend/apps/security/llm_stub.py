"""Deterministic stand-in for the shared LLM adapter (llm.complete_json).

Same interface as the real one: `complete_json(prompt, schema) -> dict`. It reads the
fenced data blocks that guard.py and critic.py put into their prompts and applies simple
heuristics, so tests and the demo run without a model. Swap the import in llmjson.py
when the real adapter lands.
"""

import json
import re

ATTACK_MARKERS = ("ignore", "ігнор", "system prompt", "системн", "jailbreak", "забудь")


def _block(prompt: str, name: str) -> str:
    match = re.search(rf"<<<{name}\n(.*?)\n{name}>>>", prompt, re.S)
    return match.group(1) if match else ""


def complete_json(prompt: str, schema: dict) -> dict:
    kind = schema.get("name")
    if kind == "guard":
        text = _block(prompt, "CLIENT_TEXT").casefold()
        attack = any(marker in text for marker in ATTACK_MARKERS)
        return {"attack": attack, "why": "heuristic stub"}
    if kind == "critic":
        return _critic(prompt)
    raise ValueError(f"unknown schema {kind!r}")


def _critic(prompt: str) -> dict:
    message = _block(prompt, "CLIENT_MESSAGE")
    plan = json.loads(_block(prompt, "PLAN") or "{}")
    context = json.loads(_block(prompt, "CONTEXT") or "{}")
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
