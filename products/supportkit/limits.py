"""Hard limits per tool: a cap on the `amount` argument and a cap on calls per customer per hour.

These are the last line of defence, checked right before a call reaches the backend.
"""

import time
from collections import defaultdict, deque


class LimitError(Exception):
    pass


class Limits:
    def __init__(self):
        self._calls: dict[tuple[int, str], deque[float]] = defaultdict(deque)

    def check(
        self,
        customer_id: int,
        tool: str,
        params: dict,
        *,
        max_amount: float | None,
        per_hour: int | None,
    ) -> None:
        if max_amount is not None:
            amount = params.get("amount")
            if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
                raise LimitError("Сума має бути додатним числом")
            if amount > max_amount:
                raise LimitError(f"Сума перевищує ліміт {max_amount:g}")
        if per_hour is not None:
            calls = self._calls[(customer_id, tool)]
            while calls and calls[0] < time.time() - 3600:
                calls.popleft()
            if len(calls) >= per_hour:
                raise LimitError("Забагато таких дій за годину")

    def record(self, customer_id: int, tool: str) -> None:
        self._calls[(customer_id, tool)].append(time.time())
