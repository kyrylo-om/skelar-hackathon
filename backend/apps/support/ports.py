"""Seam between human review and the actions module.

The review code calls `execute` after an operator approves an action. The real
implementation lives with the policy/actions work and replaces this stub.
"""


class ExecutionError(Exception):
    """The action could not be performed; the review must stay pending."""


def execute(action: str, params: dict) -> None:
    return None
