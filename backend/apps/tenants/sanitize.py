"""What leaves the product (API responses) and what we keep (the journal) is cleaned first.

A product's answer is untrusted data: it can carry text that looks like instructions, personal
data, or secrets. Before the model or the journal sees it, sensitive keys are dropped, personal
data in text is masked and the size is capped.
"""

import json
import re

from apps.security.guard import mask_pii

MAX_CHARS = 3000
SECRET_KEYS = re.compile(r"token|secret|password|passwd|api[_-]?key|authorization|cvv|card", re.I)


def _clean(value):
    if isinstance(value, dict):
        return {
            key: "[hidden]" if SECRET_KEYS.search(str(key)) else _clean(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, str):
        return mask_pii(value)
    return value


def sanitize(value, max_chars: int = MAX_CHARS):
    """The same data without secrets or personal data, cut down to `max_chars` of JSON."""
    cleaned = _clean(value)
    text = json.dumps(cleaned, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return cleaned
    return {"truncated": text[:max_chars]}
