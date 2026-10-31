"""Seam between human review and the actions module.

The review code calls `execute` after an operator approves an action. The real
implementation lives with the policy/actions work and replaces this stub.
"""


class ExecutionError(Exception):
    """The action could not be performed; the review must stay pending."""


def execute(action: str, params: dict) -> None:
    return None


def run_pipeline(chat, message) -> None:
    """Handle a new customer message. Replaced by the agent pipeline.

    Until it exists, hand the conversation to a human so nothing is lost.
    """
    from . import services

    services.add_message(
        chat,
        "ai",
        "Дякуємо за звернення! Ваш запит передано спеціалісту, він відповість у цьому чаті.",
    )
    services.escalate(chat)
