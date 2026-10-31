import pytest

from execution.identity import sign
from execution.products import Product
from execution.proposals import Proposals
from execution.server import create_server
from execution.tests.conftest import agent, backend, data, error_text

pytestmark = pytest.mark.anyio


async def order(server, number, customer="s-201"):
    async with agent(server, "shopx", customer) as mcp:
        return data(await mcp.call_tool("read", {"path": f"/orders/{number}"}))


async def propose(server, customer, path, method="POST", body=None):
    async with agent(server, "shopx", customer) as mcp:
        args = {"method": method, "path": path, "summary": f"{method} {path}", "body": body}
        return data(await mcp.call_tool("propose_call", args))["proposal_id"]


async def test_no_tool_lets_the_model_name_a_product_or_customer(server):
    async with agent(server, "shopx", "s-201") as mcp:
        tools = (await mcp.list_tools()).tools
    assert {t.name for t in tools} == {"get_product_context", "read", "propose_call"}
    for tool in tools:
        params = set(tool.input_schema.get("properties", {}))
        assert not {p for p in params if "customer" in p or "tenant" in p or p == "ctx"}


@pytest.mark.parametrize("token", [None, "garbage", "shopx.s-201.1.sig"])
async def test_no_valid_token_no_access(server, token, audit_log):
    async with agent(server, token=token) as mcp:
        result = await mcp.call_tool("read", {"path": "/orders"})
    assert error_text(result).endswith("Could not identify the customer")
    assert audit_log()[-1]["outcome"] == "denied"


async def test_token_signed_with_another_secret(server, monkeypatch):
    monkeypatch.setenv("EXECUTION_SECRET", "attacker")
    token = sign("shopx", "s-202")
    monkeypatch.setenv("EXECUTION_SECRET", "test-secret")
    async with agent(server, token=token) as mcp:
        assert (await mcp.call_tool("read", {"path": "/orders"})).is_error


async def test_unknown_product(server):
    async with agent(server, "acme", "u-1") as mcp:
        result = await mcp.call_tool("get_product_context", {})
    assert error_text(result).endswith("This product is not connected")


async def test_context_is_the_products_own_text(server, products):
    async with agent(server, "cloudbox", "c-101") as mcp:
        context = data(await mcp.call_tool("get_product_context", {}))
    assert context == products["cloudbox"].context
    assert "CREATE TABLE payments" in context


async def test_read_acts_as_the_session_customer(server):
    async with agent(server, "cloudbox", "c-101") as mcp:
        subscription = data(await mcp.call_tool("read", {"path": "/subscription"}))
    assert subscription == {"http_status": 200, "data": subscription["data"]}
    assert subscription["data"]["plan"] == "Free"
    assert (await order(server, "2001"))["http_status"] == 404  # someone else's order


@pytest.mark.parametrize(
    "path",
    ["http://evil.example/x", "//evil.example/x", "orders", "/../admin", "/%2e%2e/admin", "/a b"],
)
async def test_read_stays_on_the_products_api(server, path, audit_log):
    async with agent(server, "shopx", "s-201") as mcp:
        result = await mcp.call_tool("read", {"path": path})
    assert "plain path" in error_text(result)
    assert audit_log()[-1]["outcome"] == "denied"


async def test_proposal_runs_only_when_our_backend_executes_it(server, audit_log):
    proposal_id = await propose(server, "s-201", "/orders/1042/cancel")
    assert (await order(server, "1042"))["data"]["status"] == "processing"

    async with backend(server) as api:
        shown = (await api.get(f"/proposals/{proposal_id}")).json()
        assert shown["status"] == "proposed"
        assert (shown["tenant"], shown["customer"], shown["path"]) == (
            "shopx",
            "s-201",
            "/orders/1042/cancel",
        )
        executed = (await api.post(f"/proposals/{proposal_id}/execute")).json()

    assert executed["status"] == "executed"
    assert executed["result"]["http_status"] == 200
    assert (await order(server, "1042"))["data"]["status"] == "cancelled"
    events = [(e["event"], e["outcome"]) for e in audit_log()]
    assert ("propose", "ok") in events and ("execute", "ok") in events


@pytest.mark.parametrize("key", ["", "wrong"])
async def test_proposal_endpoints_need_the_service_key(server, key, audit_log):
    proposal_id = await propose(server, "s-201", "/orders/1042/cancel")
    async with backend(server, key) as api:
        assert (await api.get(f"/proposals/{proposal_id}")).status_code == 401
        assert (await api.post(f"/proposals/{proposal_id}/execute")).status_code == 401
    assert audit_log()[-1]["event"] == "service"
    assert (await order(server, "1042"))["data"]["status"] == "processing"


async def test_proposal_runs_once(server):
    proposal_id = await propose(
        server, "s-201", "/orders/1043/refund", body={"amount": 100, "reason": "x"}
    )
    async with backend(server) as api:
        assert (await api.post(f"/proposals/{proposal_id}/execute")).status_code == 200
        again = await api.post(f"/proposals/{proposal_id}/execute")
    assert again.status_code == 409
    assert len((await order(server, "1043"))["data"]["refunds"]) == 1


async def test_rejected_proposal_never_runs(server):
    proposal_id = await propose(server, "s-201", "/orders/1042/cancel")
    async with backend(server) as api:
        assert (await api.post(f"/proposals/{proposal_id}/reject")).json()["status"] == "rejected"
        assert (await api.post(f"/proposals/{proposal_id}/execute")).status_code == 409
    assert (await order(server, "1042"))["data"]["status"] == "processing"


async def test_expired_proposal_never_runs(products):
    server = create_server(products, Proposals(ttl=-1))
    proposal_id = await propose(server, "s-201", "/orders/1042/cancel")
    async with backend(server) as api:
        response = await api.post(f"/proposals/{proposal_id}/execute")
    assert response.status_code == 409
    assert response.json()["detail"] == "Proposal is expired"


async def test_unknown_proposal(server):
    async with backend(server) as api:
        assert (await api.post("/proposals/nope/execute")).status_code == 404


async def test_product_refusal_is_reported_not_hidden(server, audit_log):
    proposal_id = await propose(server, "s-201", "/orders/1044/cancel")  # already shipped
    async with backend(server) as api:
        executed = (await api.post(f"/proposals/{proposal_id}/execute")).json()
    assert executed["status"] == "failed"
    assert executed["result"]["http_status"] == 409
    assert audit_log()[-1]["outcome"] == "failed"


async def test_execution_acts_as_the_customer_who_proposed(server):
    # s-201 proposes cancelling s-202's order: the product sees s-201 and refuses.
    proposal_id = await propose(server, "s-201", "/orders/2001/cancel")
    async with backend(server) as api:
        executed = (await api.post(f"/proposals/{proposal_id}/execute")).json()
    assert executed["result"]["http_status"] == 404
    assert (await order(server, "2001", customer="s-202"))["data"]["status"] == "processing"


async def test_propose_only_accepts_state_changing_methods(server):
    async with agent(server, "shopx", "s-201") as mcp:
        result = await mcp.call_tool(
            "propose_call", {"method": "GET", "path": "/orders", "summary": "x"}
        )
    assert result.is_error


async def test_unreachable_product(audit_log):
    down = Product("shopx", "http://127.0.0.1:9", "key", "ctx")
    async with agent(create_server({"shopx": down}), "shopx", "s-201") as mcp:
        result = await mcp.call_tool("read", {"path": "/orders"})
    assert error_text(result).endswith("The product is not reachable")
    assert audit_log()[-1]["outcome"] == "failed"
