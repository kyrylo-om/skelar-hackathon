"""Seam between human review and the rest of the system.

`execute` runs an action after an operator approved it, and `run_pipeline` handles a new customer
message. Both hand over to the orchestrator when ORCHESTRATOR_ENABLED is on; with it off the
chat simply passes every message to a human.
"""


class ExecutionError(Exception):
    """The action could not be performed; the review must stay pending."""


def execute(action: str, params: dict, customer=None) -> None:
    """Run an action a human approved. The orchestrator re-checks Policy first, then acts."""
    from django.conf import settings

    if settings.ORCHESTRATOR_ENABLED and customer is not None:
        from apps.orchestrator.pipeline import execute_approved

        execute_approved(customer, action, params)


def run_pipeline(chat, message) -> None:
    """Handle a new customer message; without the orchestrator, hand it to a human."""
    from django.conf import settings

    from . import services

    if settings.ORCHESTRATOR_ENABLED:
        from apps.orchestrator.pipeline import handle_customer_message

        handle_customer_message(chat, message)
        return

    services.add_message(
        chat,
        "ai",
        "Дякуємо за звернення! Ваш запит передано спеціалісту, він відповість у цьому чаті.",
    )
    services.escalate(chat)
