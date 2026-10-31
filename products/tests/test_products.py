"""One happy path and one refusal per product tool family."""

import pytest

import shop.api
import shop.server
import subscriptions.api
import subscriptions.server
from tests.conftest import confirm, data, error_text, mcp_client

pytestmark = pytest.mark.anyio


@pytest.fixture
def shop_kit():
    return shop.server.create_kit(shop.api.create_app())


@pytest.fixture
def subs_kit():
    return subscriptions.server.create_kit(subscriptions.api.create_app())


async def call_and_confirm(kit, tool, params, customer_id=7):
    async with mcp_client(kit, customer_id) as mcp:
        pending = data(await mcp.call_tool(tool, params))
    return await confirm(kit, pending["confirmation_id"], customer_id)


async def test_shop_change_address(shop_kit):
    response = await call_and_confirm(
        shop_kit, "change_address", {"order_id": "1042", "address": "Одеса, вул. Дерибасівська, 3"}
    )
    assert response.json()["result"]["address"] == "Одеса, вул. Дерибасівська, 3"


async def test_shop_cancel_order(shop_kit):
    response = await call_and_confirm(shop_kit, "cancel_order", {"order_id": "1042"})
    assert response.json()["result"]["status"] == "cancelled"


async def test_shop_refund_only_delivered(shop_kit):
    response = await call_and_confirm(
        shop_kit, "refund", {"order_id": "1044", "amount": 50, "reason": "x"}
    )
    assert response.status_code == 409


async def test_shop_cannot_act_on_other_customers_order(shop_kit):
    response = await call_and_confirm(shop_kit, "cancel_order", {"order_id": "2001"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Не знайдено"


async def test_subscriptions_lists_only_own(subs_kit):
    async with mcp_client(subs_kit, 7) as mcp:
        subs = data(await mcp.call_tool("list_subscriptions", {}))
        invoices = data(await mcp.call_tool("list_invoices", {}))
    assert [s["id"] for s in subs] == ["sub-1"]
    assert {i["id"] for i in invoices} == {"inv-501", "inv-502"}


async def test_subscriptions_pause(subs_kit):
    response = await call_and_confirm(
        subs_kit, "pause_subscription", {"subscription_id": "sub-1", "months": 2}
    )
    assert response.json()["result"]["status"] == "paused"


async def test_subscriptions_pause_too_long(subs_kit):
    async with mcp_client(subs_kit, 7) as mcp:
        result = await mcp.call_tool(
            "pause_subscription", {"subscription_id": "sub-1", "months": 6}
        )
    assert result.is_error


async def test_subscriptions_cancel(subs_kit):
    response = await call_and_confirm(subs_kit, "cancel_subscription", {"subscription_id": "sub-1"})
    assert response.json()["result"]["status"] == "cancelled"


async def test_subscriptions_refund_cap(subs_kit):
    async with mcp_client(subs_kit, 7) as mcp:
        result = await mcp.call_tool(
            "refund_invoice", {"invoice_id": "inv-501", "amount": 600, "reason": "x"}
        )
    assert "ліміт" in error_text(result)


async def test_subscriptions_refund(subs_kit):
    response = await call_and_confirm(
        subs_kit, "refund_invoice", {"invoice_id": "inv-501", "amount": 299, "reason": "x"}
    )
    assert response.json()["result"]["refunded"] == 299
