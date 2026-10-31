"""The shared security rules, exercised through the shop product over real MCP-over-HTTP."""

import pytest

from shop.api import create_app
from shop.server import create_kit
from subscriptions.api import create_app as create_subscriptions_app
from subscriptions.server import create_kit as create_subscriptions_kit
from supportkit.identity import sign
from tests.conftest import confirm, data, error_text, mcp_client

pytestmark = pytest.mark.anyio


@pytest.fixture
def kit():
    return create_kit(create_app())


async def refunded(kit, order_id="1043"):
    async with mcp_client(kit, 7) as mcp:
        return data(await mcp.call_tool("get_order", {"order_id": order_id}))["refunded"]


@pytest.mark.parametrize(
    "product", [(create_kit, create_app), (create_subscriptions_kit, create_subscriptions_app)]
)
async def test_no_tool_lets_the_model_name_a_customer(product):
    create, app = product
    async with mcp_client(create(app()), 7) as mcp:
        tools = (await mcp.list_tools()).tools
    assert tools
    for tool in tools:
        params = tool.input_schema.get("properties", {})
        assert not [p for p in params if "customer" in p or p in ("api", "ctx")], tool.name


async def test_call_without_token_is_refused_and_audited(kit, audit_log):
    async with mcp_client(kit) as mcp:
        result = await mcp.call_tool("list_orders", {})
    assert "особу" in error_text(result)
    assert audit_log()[-1] | {"at": None} == {
        "at": None,
        "server": "shop",
        "tool": "list_orders",
        "customer_id": None,
        "params": {},
        "outcome": "denied",
        "detail": "malformed token",
    }


async def test_forged_token_is_refused(kit, monkeypatch):
    monkeypatch.setenv("SUPPORTKIT_SECRET", "attacker")
    token = sign(8)
    monkeypatch.setenv("SUPPORTKIT_SECRET", "test-secret")
    async with mcp_client(kit, token=token) as mcp:
        result = await mcp.call_tool("get_order", {"order_id": "2001"})
    assert result.is_error


async def test_only_own_records_are_visible(kit, audit_log):
    async with mcp_client(kit, 7) as mcp:
        orders = data(await mcp.call_tool("list_orders", {}))
        other = await mcp.call_tool("get_order", {"order_id": "2001"})
    assert {o["id"] for o in orders} == {"1042", "1043", "1044"}
    assert error_text(other).endswith("Не знайдено")
    assert audit_log()[-1]["outcome"] == "error"


async def test_risky_tool_waits_for_the_customer(kit, audit_log):
    async with mcp_client(kit, 7) as mcp:
        pending = data(
            await mcp.call_tool("refund", {"order_id": "1043", "amount": 30, "reason": "подряпина"})
        )
    assert pending["status"] == "confirmation_required"
    assert pending["summary"] == "Повернути 30 грн за замовлення №1043"
    assert await refunded(kit) == 0

    response = await confirm(kit, pending["confirmation_id"], 7)
    assert response.status_code == 200
    assert response.json()["result"]["refunded"] == 30
    assert await refunded(kit) == 30
    outcomes = [(e["tool"], e["outcome"]) for e in audit_log()]
    assert ("refund", "pending") in outcomes and ("refund", "ok") in outcomes


async def test_confirmation_is_single_use(kit):
    async with mcp_client(kit, 7) as mcp:
        pending = data(
            await mcp.call_tool("refund", {"order_id": "1043", "amount": 30, "reason": "x"})
        )
    assert (await confirm(kit, pending["confirmation_id"], 7)).status_code == 200
    assert (await confirm(kit, pending["confirmation_id"], 7)).status_code == 404
    assert await refunded(kit) == 30


async def test_confirmation_belongs_to_its_customer(kit):
    async with mcp_client(kit, 7) as mcp:
        pending = data(
            await mcp.call_tool("refund", {"order_id": "1043", "amount": 30, "reason": "x"})
        )
    assert (await confirm(kit, pending["confirmation_id"])).status_code == 401
    assert (await confirm(kit, pending["confirmation_id"], 8)).status_code == 404
    assert await refunded(kit) == 0
    # The owner can still confirm it.
    assert (await confirm(kit, pending["confirmation_id"], 7)).status_code == 200


async def test_expired_confirmation(monkeypatch):
    monkeypatch.setenv("SUPPORTKIT_CONFIRM_TTL", "-1")
    kit = create_kit(create_app())
    async with mcp_client(kit, 7) as mcp:
        pending = data(
            await mcp.call_tool("refund", {"order_id": "1043", "amount": 30, "reason": "x"})
        )
    assert (await confirm(kit, pending["confirmation_id"], 7)).status_code == 404
    assert await refunded(kit) == 0


async def test_amount_cap(kit, audit_log):
    async with mcp_client(kit, 7) as mcp:
        result = await mcp.call_tool("refund", {"order_id": "1043", "amount": 1200, "reason": "x"})
    assert "ліміт" in error_text(result)
    assert audit_log()[-1]["outcome"] == "denied"


async def test_schema_rejects_bad_arguments(kit):
    async with mcp_client(kit, 7) as mcp:
        result = await mcp.call_tool("refund", {"order_id": "1043", "amount": -5, "reason": "x"})
    assert result.is_error


async def test_hourly_cap(kit):
    async with mcp_client(kit, 7) as mcp:
        for _ in range(3):
            pending = data(
                await mcp.call_tool("refund", {"order_id": "1043", "amount": 10, "reason": "x"})
            )
            assert (await confirm(kit, pending["confirmation_id"], 7)).status_code == 200
        result = await mcp.call_tool("refund", {"order_id": "1043", "amount": 10, "reason": "x"})
    assert "Забагато" in error_text(result)
    assert await refunded(kit) == 30


async def test_backend_refusal_reaches_the_confirmer(kit):
    async with mcp_client(kit, 7) as mcp:
        pending = data(await mcp.call_tool("cancel_order", {"order_id": "1044"}))
    response = await confirm(kit, pending["confirmation_id"], 7)
    assert response.status_code == 409
    assert response.json()["detail"] == "Скасувати можна лише замовлення в обробці"
