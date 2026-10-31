import contextlib
import json

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from supportkit import TOKEN_HEADER
from supportkit.identity import sign

BASE = "http://127.0.0.1:9000"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def audit_log(monkeypatch, tmp_path):
    path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("SUPPORTKIT_SECRET", "test-secret")
    monkeypatch.setenv("SUPPORTKIT_AUDIT_LOG", str(path))

    def read():
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    return read


@contextlib.asynccontextmanager
async def http(kit, customer_id: int | None = None, token: str | None = None):
    """HTTP client for the kit's app, in process, sending the customer's token if given."""
    app = kit.http_app()
    if token is None and customer_id is not None:
        token = sign(customer_id)
    headers = {TOKEN_HEADER: token} if token else {}
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=BASE, headers=headers
        ) as client:
            yield client


@contextlib.asynccontextmanager
async def mcp_client(kit, customer_id: int | None = None, token: str | None = None):
    """An MCP client connected to the kit over streamable HTTP, like the real agent."""
    async with http(kit, customer_id, token) as client:
        async with Client(streamable_http_client(f"{BASE}/mcp", http_client=client)) as mcp:
            yield mcp


def data(result):
    """The tool's return value, from structured content when the SDK made it, else the text."""
    assert not result.is_error, result.content
    content = result.structured_content
    if content is None:
        return json.loads(result.content[0].text)
    return content["result"] if set(content) == {"result"} else content


def error_text(result) -> str:
    assert result.is_error
    return result.content[0].text


async def confirm(kit, confirmation_id: str, customer_id: int | None = None):
    """What the chat UI does when the customer presses "confirm"."""
    async with http(kit, customer_id) as client:
        return await client.post(f"/confirm/{confirmation_id}")
