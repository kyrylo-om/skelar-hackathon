"""A product's API, read from the product's own context text.

Products hand us a text context with an API table (| Method | Path | Body | Result |). We do not
write endpoint lists by hand: this module parses that table, so connecting a product means
connecting its documentation. Whether a call is safe is not in the table (products give us no
risk levels); that is our side's rules (manifest.py) and, without a rule, the answer is "a human".
"""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
VAR = re.compile(r"\{(\w+)\}")
SAFE_VALUE = re.compile(r"[\w.\-]{1,80}")
ROW = re.compile(r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*`?([^|`]+?)`?\s*\|([^|]*)\|(.*)\|\s*$")


class EndpointError(ValueError):
    """The call is not one the product's API describes, or its values are not acceptable."""


@dataclass(frozen=True)
class Endpoint:
    id: str
    method: str
    path: str  # like /payments/{payment_id}/refund
    description: str = ""
    body_example: dict = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return "read" if self.method == "GET" else "write"

    @property
    def key(self) -> str:
        """How rules refer to it: "POST /subscription/sync"."""
        return f"{self.method} {self.path}"

    @property
    def path_vars(self) -> tuple[str, ...]:
        return tuple(VAR.findall(self.path))


def slug(method: str, path: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "_", VAR.sub(r"\1", path).lower()).strip("_")
    return f"{method.lower()}_{words or 'root'}"


def parse_api(context: str) -> dict[str, Endpoint]:
    """Endpoints by id, from every API-table row in the context text."""
    found = {}
    for line in context.splitlines():
        match = ROW.match(line.strip())
        if not match:
            continue
        method, path, body, result = match.groups()
        path = path.strip()
        example = {}
        text = body.strip().strip("`")
        if text:
            try:
                value = json.loads(text)
                example = value if isinstance(value, dict) else {}
            except ValueError:
                example = {}
        endpoint = Endpoint(slug(method, path), method, path, result.strip(), example)
        found[endpoint.id] = endpoint
    if not found:
        raise EndpointError("the context has no API table")
    return found


def _check_value(name: str, value) -> str:
    text = str(value)
    if isinstance(value, bool) or not SAFE_VALUE.fullmatch(text):
        raise EndpointError(f"parameter {name} is not a plain identifier")
    return text


def build_path(endpoint: Endpoint, params: dict) -> str:
    """The concrete path: every path variable filled from `params`, nothing else accepted."""
    if set(params) - set(endpoint.path_vars):
        raise EndpointError(
            f"unexpected path parameters {sorted(set(params) - set(endpoint.path_vars))}"
        )
    path = endpoint.path
    for name in endpoint.path_vars:
        if name not in params:
            raise EndpointError(f"path parameter {name} is missing")
        path = path.replace("{" + name + "}", quote(_check_value(name, params[name]), safe=""))
    return path


def check_body(endpoint: Endpoint, body: dict) -> dict:
    """The body may only hold fields the API documents, with scalar values."""
    if not isinstance(body, dict):
        raise EndpointError("body must be an object")
    unknown = set(body) - set(endpoint.body_example)
    if unknown:
        raise EndpointError(f"unexpected body fields {sorted(unknown)}")
    for name, value in body.items():
        if isinstance(value, (dict, list)):
            raise EndpointError(f"body field {name} must be a plain value")
        expected = endpoint.body_example[name]
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EndpointError(f"body field {name} must be a number")
        elif isinstance(expected, str) and not isinstance(value, str):
            raise EndpointError(f"body field {name} must be text")
    return body
