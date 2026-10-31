import contextlib
import json

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from execution.identity import TOKEN_HEADER, sign
from execution.products import Product
from execution.server import create_server
from mocks.cloudbox.app import HERE as CLOUDBOX
from mocks.cloudbox.app import create_app as cloudbox_app
from mocks.shopx.app import HERE as SHOPX
from mocks.shopx.app import create_app as shopx_app

BASE = "http://127.0.0.1:9000"
SERVICE_KEY = "test-service-key"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def audit_log(monkeypatch, tmp_path):
    path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("EXECUTION_SECRET", "test-secret")
    monkeypatch.setenv("EXECUTION_SERVICE_KEY", SERVICE_KEY)
    monkeypatch.setenv("EXECUTION_AUDIT_LOG", str(path))

    def read():
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    return read


@pytest.fixture
def products(tmp_path):
    """Both mock products, called in process, each on a fresh database."""
    apps = {
        "cloudbox": (cloudbox_app(tmp_path / "cloudbox.sqlite3", "cloudbox-key"), CLOUDBOX),
        "shopx": (shopx_app(tmp_path / "shopx.sqlite3", "shopx-key"), SHOPX),
    }
    return {
        name: Product(
            name,
            f"http://{name}",
            f"{name}-key",
            (folder / "context.md").read_text(encoding="utf-8"),
            httpx2.ASGITransport(app=app),
        )
        for name, (app, folder) in apps.items()
    }


@pytest.fixture
def server(products):
    return create_server(products)


@contextlib.asynccontextmanager
async def http(server, headers: dict | None = None):
    """HTTP client for the server's app, in process."""
    app = server.streamable_http_app(stateless_http=True)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=BASE, headers=headers or {}
        ) as client:
            yield client


@contextlib.asynccontextmanager
async def agent(server, tenant: str | None = None, customer: str | None = None, token=None):
    """An MCP client, as the agent sees the server, for this customer's session."""
    if token is None and tenant:
        token = sign(tenant, customer)
    async with http(server, {TOKEN_HEADER: token} if token else {}) as client:
        async with Client(streamable_http_client(f"{BASE}/mcp", http_client=client)) as mcp:
            yield mcp


@contextlib.asynccontextmanager
async def backend(server, key: str = SERVICE_KEY):
    """Our backend's view: the proposal endpoints with the service key."""
    async with http(server, {"Authorization": f"Bearer {key}"}) as client:
        yield client


def data(result):
    assert not result.is_error, result.content
    content = result.structured_content
    if content is None:
        return json.loads(result.content[0].text)
    return content["result"] if set(content) == {"result"} else content


def error_text(result) -> str:
    assert result.is_error
    return result.content[0].text
