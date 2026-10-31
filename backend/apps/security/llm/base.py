"""LLM adapter: strict JSON out, fail closed.

`complete_json` never raises. If the model is unreachable, answers with invalid JSON or
the per-message call budget is spent, it returns the caller's safe `default` (marked with
`_fallback: True`), so a failure can only ever make the system more cautious.

The API key is read from settings only to build the client. It is never logged or returned.
"""

import json
import logging
import math
import time
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings

logger = logging.getLogger("apps.security.llm")

# Roles that need some variety; everything else is deterministic.
TEMPERATURE = {"responder": 0.3}

# Calls made for the current customer message; None outside a message budget.
_budget: ContextVar[list | None] = ContextVar("llm_budget", default=None)


class LLMNetworkError(Exception):
    """The provider could not be reached in time; worth one retry."""


class LLMError(Exception):
    """The provider refused or failed; not retried."""


@contextmanager
def message_budget():
    """Count LLM calls for one customer message. Nested use shares the outer budget."""
    if _budget.get() is not None:
        yield
        return
    token = _budget.set([0, time.monotonic()])  # [calls made, start of the message]
    try:
        yield
    finally:
        _budget.reset(token)


def _take_call() -> bool:
    counter = _budget.get()
    if counter is None:
        return True
    if counter[0] >= settings.LLM_MAX_CALLS_PER_MESSAGE:
        return False
    if time.monotonic() - counter[1] >= settings.LLM_TOTAL_DEADLINE_SEC:
        return False  # the whole message has used up its time
    counter[0] += 1
    return True


def _call_timeout() -> float:
    """Per-call timeout, never longer than what is left of the message's overall deadline."""
    counter = _budget.get()
    if counter is None:
        return settings.LLM_TIMEOUT
    left = settings.LLM_TOTAL_DEADLINE_SEC - (time.monotonic() - counter[1])
    return max(1.0, min(settings.LLM_TIMEOUT, left))


_TYPES = {
    "string": str,
    "boolean": bool,
    "array": list,
    "object": dict,
    "number": (int, float),
    "null": type(None),
}


def _type_ok(value, allowed) -> bool:
    names = allowed if isinstance(allowed, list) else [allowed]
    for name in names:
        expected = _TYPES[name]
        if name == "number" and (isinstance(value, bool) or not math.isfinite(value)):
            continue  # booleans, NaN and infinity are not numbers here
        if isinstance(value, expected):
            return True
    return False


def validate(data, schema: dict) -> bool:
    """Check required keys, types and enums by hand. Unknown keys are dropped by the caller."""
    if not isinstance(data, dict):
        return False
    for key in schema.get("required", []):
        if key not in data:
            return False
    for key, rule in schema.get("properties", {}).items():
        if key not in data:
            continue
        value = data[key]
        if "type" in rule and not _type_ok(value, rule["type"]):
            return False
        if "enum" in rule and value not in rule["enum"]:
            return False
        if "minimum" in rule and value < rule["minimum"]:
            return False
        if "maximum" in rule and value > rule["maximum"]:
            return False
    return True


def _deepseek_call(role: str, system: str, user: str) -> str:
    import openai  # imported lazily so mock mode needs no network client

    client = openai.OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        timeout=_call_timeout(),
        max_retries=0,  # retries are ours, so they are counted
    )
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=TEMPERATURE.get(role, 0.0),
            max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
        )
    except openai.APIConnectionError as exc:  # includes timeouts
        raise LLMNetworkError(type(exc).__name__) from None
    except openai.APIError as exc:
        raise LLMError(type(exc).__name__) from None
    choice = response.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        logger.warning("llm role=%s output hit the token limit and was cut off", role)
    return choice.message.content or ""


def _provider_call(role: str, system: str, user: str) -> str:
    if settings.LLM_PROVIDER == "deepseek":
        if not settings.LLM_API_KEY:
            raise LLMError("missing_api_key")
        return _deepseek_call(role, system, user)
    from . import mock

    return mock.respond(role, system, user)


def _parse(raw: str, schema: dict) -> dict | None:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not validate(data, schema):
        return None
    allowed = schema.get("properties", {})
    return {key: value for key, value in data.items() if key in allowed}


def complete_json(system: str, user: str, schema: dict, role: str, default: dict) -> dict:
    started = time.monotonic()
    outcome = "invalid"
    result = None
    for _attempt in range(2):  # one call plus at most one retry
        if not _take_call():
            outcome = "budget_exceeded"
            break
        try:
            raw = _provider_call(role, system, user)
        except LLMNetworkError:
            outcome = "network_error"
            continue
        except LLMError as exc:
            outcome = f"error:{exc}"
            break
        result = _parse(raw, schema)
        if result is not None:
            outcome = "ok"
            break
        outcome = "invalid"
    valid = result is not None
    logger.info(
        "llm role=%s model=%s ms=%d valid=%s outcome=%s",
        role,
        settings.LLM_MODEL if settings.LLM_PROVIDER != "mock" else "mock",
        (time.monotonic() - started) * 1000,
        valid,
        outcome,
    )
    if valid:
        return result
    return {**default, "_fallback": True}
