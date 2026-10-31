"""Connected products. A product hands us only an HTTP API, an API key and a text context.

The context is free text (what the product is, its support rules, its API, its database schema)
and is given to the agent as is. Nothing here comes with risk levels: whether an action may run
is decided on our side, by independent reviewers, before anyone calls execute.

products.toml:
    [shopx]
    base_url = "http://127.0.0.1:9202"
    api_key_env = "SHOPX_API_KEY"         # the key itself never sits in the file
    context = "../mocks/shopx/context.md" # relative to products.toml

Every product is called as `Authorization: Bearer <api key>` plus `X-Customer-Id: <customer>`.
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import httpx2

MAX_PATH = 500


@dataclass(frozen=True)
class Product:
    name: str
    base_url: str
    api_key: str
    context: str
    transport: httpx2.AsyncBaseTransport | None = None  # tests call the product in process


def load(path: Path) -> dict[str, Product]:
    """Read products.toml. Fails closed: a missing key or context stops the server from starting."""
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    products = {}
    for name, entry in config.items():
        api_key = os.environ.get(entry["api_key_env"])
        if not api_key:
            raise RuntimeError(f"{name}: {entry['api_key_env']} is not set")
        context = (path.parent / entry["context"]).read_text(encoding="utf-8")
        products[name] = Product(name, entry["base_url"], api_key, context)
    return products


def check_path(path: str) -> str:
    """Only a path on the product's own API: never another host, never `..`."""
    route = path.split("?", 1)[0]
    if (
        not path.startswith("/")
        or path.startswith("//")
        or len(path) > MAX_PATH
        or any(ch.isspace() or ord(ch) < 32 or ch in "\\#" for ch in path)
        or any(unquote(segment) in (".", "..") for segment in route.split("/"))
    ):
        raise ValueError("path must be a plain path on the product's API, like /orders/1042")
    return path


async def call(product: Product, customer: str, method: str, path: str, body=None):
    """One request to the product as `customer`: (status, JSON or text). Raises HTTPError."""
    headers = {"Authorization": f"Bearer {product.api_key}", "X-Customer-Id": customer}
    async with httpx2.AsyncClient(
        base_url=product.base_url, transport=product.transport, headers=headers, timeout=10
    ) as http:
        response = await http.request(method, check_path(path), json=body)
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, response.text[:2000]
