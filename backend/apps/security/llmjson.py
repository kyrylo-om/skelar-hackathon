"""Calling the LLM for strict JSON, with one retry and fenced client text."""

from collections.abc import Callable
from typing import TypeVar

from . import llm_stub as llm  # replace with the shared adapter when it exists

T = TypeVar("T")

FENCE_WORDS = ("CLIENT_TEXT", "CLIENT_MESSAGE", "PLAN", "CONTEXT")


def fence(name: str, body: str) -> str:
    """Wrap untrusted data in a delimited block the prompt marks as data, not instructions."""
    for word in FENCE_WORDS:
        body = body.replace(word, "")
    return f"<<<{name}\n{body}\n{name}>>>"


def ask_json(prompt: str, schema: dict, validate: Callable[[dict], T]) -> T | None:
    """Return the validated answer, or None if two attempts gave invalid JSON."""
    for _ in range(2):
        try:
            return validate(llm.complete_json(prompt, schema))
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return None
