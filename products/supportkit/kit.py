"""Kit: everything a mock product's MCP server shares, so a product only writes its tools.

    kit = Kit("shop", "http://127.0.0.1:9101")   # or the fake backend's ASGI app, in tests

    @kit.tool(confirm="Скасувати замовлення {order_id}", per_hour=5)
    async def cancel_order(api: ApiClient, order_id: str) -> dict:
        '''Cancel one of the customer's orders.'''
        return await api.post(f"/orders/{order_id}/cancel")

Every tool call:
  1. takes the customer from the signed X-Customer-Token header (identity.py);
  2. passes the hard limits (limits.py);
  3. with `confirm`, is parked and returns a confirmation id instead of running (confirm.py);
     the customer confirms through POST /confirm/{id}, an HTTP route the model cannot call;
  4. runs with `api`, a backend client already bound to that customer;
  5. lands in the audit log (audit.py), whatever the outcome.
`api` is hidden from the tool schema, so the model has no way to name a customer.
"""

import asyncio
import inspect
import typing
from collections.abc import Callable
from dataclasses import dataclass

import httpx2
import uvicorn
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import audit, identity
from .confirm import Confirmations
from .limits import LimitError, Limits

TOKEN_HEADER = "X-Customer-Token"
# Kit -> fake backend only. The backend trusts it the way an internal service would.
CUSTOMER_HEADER = "X-Customer-Id"

INSTRUCTIONS = (
    "All tools act on behalf of the current customer only; you cannot choose the customer. "
    "A tool that changes something returns status 'confirmation_required' with a summary: "
    "show the summary to the customer and stop. The customer confirms it in the chat UI, "
    "not through you. Never claim such an action is done before it is confirmed."
)


class ApiClient:
    """Client for the product's backend, bound to one customer. Backend errors become ToolErrors."""

    def __init__(self, base_url: str, transport: httpx2.AsyncBaseTransport | None, customer_id):
        self._base_url = base_url
        self._transport = transport
        self._headers = {CUSTOMER_HEADER: str(customer_id)}

    async def get(self, path: str):
        return await self._request("GET", path)

    async def post(self, path: str, json: dict | None = None):
        return await self._request("POST", path, json)

    async def _request(self, method: str, path: str, json: dict | None = None):
        try:
            async with httpx2.AsyncClient(
                base_url=self._base_url, transport=self._transport, headers=self._headers
            ) as http:
                response = await http.request(method, path, json=json)
        except httpx2.HTTPError as exc:
            raise ToolError("Сервіс тимчасово недоступний") from exc
        if response.status_code >= 400:
            raise ToolError(response.json().get("detail", "Запит відхилено"))
        return response.json()


@dataclass(frozen=True)
class _Tool:
    fn: Callable
    confirm: str | None
    max_amount: float | None
    per_hour: int | None


class Kit:
    def __init__(self, name: str, api, instructions: str = ""):
        """`api` is the backend's base URL, or its ASGI app to call it in-process."""
        self.name = name
        self.server = MCPServer(name, instructions=f"{INSTRUCTIONS}\n\n{instructions}".strip())
        if isinstance(api, str):
            self._api_url, self._api_transport = api, None
        else:
            self._api_url, self._api_transport = "http://backend", httpx2.ASGITransport(app=api)
        self._tools: dict[str, _Tool] = {}
        self._limits = Limits()
        self._confirmations = Confirmations()
        self.server.custom_route("/confirm/{confirmation_id}", methods=["POST"])(self._confirm)

    def tool(
        self,
        *,
        confirm: str | None = None,
        max_amount: float | None = None,
        per_hour: int | None = None,
    ):
        """Register `fn(api, **params)` as an MCP tool.

        confirm:    summary shown to the customer, formatted with the call's params; when set,
                    the call waits for the customer's confirmation.
        max_amount: cap on the `amount` param.
        per_hour:   cap on calls per customer per hour.
        """

        def decorator(fn):
            name = fn.__name__
            self._tools[name] = _Tool(fn, confirm, max_amount, per_hour)

            async def wrapper(ctx: Context, **params):
                return await self._call(name, ctx.headers, params)

            # Same schema as `fn`, minus `api`, plus the Context the SDK injects.
            hints = typing.get_type_hints(fn, include_extras=True)
            visible = [
                p.replace(annotation=hints.get(p.name, p.annotation))
                for p in inspect.signature(fn).parameters.values()
                if p.name != "api"
            ]
            returns = dict if confirm else hints.get("return", typing.Any)
            ctx = inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=Context)
            wrapper.__name__ = wrapper.__qualname__ = name
            wrapper.__signature__ = inspect.Signature([*visible, ctx], return_annotation=returns)
            wrapper.__annotations__ = {p.name: p.annotation for p in visible} | {
                "ctx": Context,
                "return": returns,
            }
            self.server.add_tool(wrapper, name=name, description=fn.__doc__)
            return fn

        return decorator

    def http_app(self):
        return self.server.streamable_http_app(stateless_http=True)

    async def _call(self, tool: str, headers, params: dict):
        try:
            customer_id = identity.verify((headers or {}).get(TOKEN_HEADER))
        except identity.IdentityError as exc:
            audit.write(self.name, tool, None, params, audit.DENIED, str(exc))
            raise ToolError("Не вдалося встановити особу клієнта") from exc

        spec = self._tools[tool]
        if spec.confirm is None:
            return await self._execute(customer_id, tool, params)

        # Refuse now what would be refused on confirmation anyway.
        self._check_limits(customer_id, tool, params)
        confirmation_id = self._confirmations.create(customer_id, tool, params)
        audit.write(self.name, tool, customer_id, params, audit.PENDING, confirmation_id)
        return {
            "status": "confirmation_required",
            "confirmation_id": confirmation_id,
            "summary": spec.confirm.format(**params),
            "expires_in": self._confirmations.ttl,
        }

    def _check_limits(self, customer_id: int, tool: str, params: dict) -> None:
        spec = self._tools[tool]
        try:
            self._limits.check(
                customer_id, tool, params, max_amount=spec.max_amount, per_hour=spec.per_hour
            )
        except LimitError as exc:
            audit.write(self.name, tool, customer_id, params, audit.DENIED, str(exc))
            raise ToolError(str(exc)) from exc

    async def _execute(self, customer_id: int, tool: str, params: dict):
        self._check_limits(customer_id, tool, params)
        # Attempts count towards per_hour, so probing other people's ids is limited too.
        self._limits.record(customer_id, tool)
        api = ApiClient(self._api_url, self._api_transport, customer_id)
        try:
            result = await self._tools[tool].fn(api, **params)
        except Exception as exc:
            audit.write(self.name, tool, customer_id, params, audit.ERROR, str(exc))
            raise
        audit.write(self.name, tool, customer_id, params, audit.OK)
        return result

    async def _confirm(self, request: Request) -> JSONResponse:
        """Called by the chat UI when the customer presses "confirm", never by the model."""
        confirmation_id = request.path_params["confirmation_id"]
        try:
            customer_id = identity.verify(request.headers.get(TOKEN_HEADER))
        except identity.IdentityError as exc:
            audit.write(self.name, "confirm", None, {"id": confirmation_id}, audit.DENIED, str(exc))
            return JSONResponse({"detail": "Не вдалося встановити особу клієнта"}, 401)

        pending = self._confirmations.take(confirmation_id, customer_id)
        if pending is None:
            audit.write(
                self.name, "confirm", customer_id, {"id": confirmation_id}, audit.DENIED, "unknown"
            )
            return JSONResponse({"detail": "Підтвердження не знайдено або воно застаріло"}, 404)
        try:
            result = await self._execute(customer_id, pending.tool, pending.params)
        except ToolError as exc:
            return JSONResponse({"detail": str(exc)}, 409)
        return JSONResponse({"status": "done", "tool": pending.tool, "result": result})


def run(kit: Kit, api_app, *, api_port: int, mcp_port: int) -> None:
    """Serve the fake backend and the MCP server side by side (local dev and demo)."""

    async def serve():
        servers = [
            uvicorn.Server(uvicorn.Config(api_app, host="127.0.0.1", port=api_port)),
            uvicorn.Server(uvicorn.Config(kit.http_app(), host="127.0.0.1", port=mcp_port)),
        ]
        await asyncio.gather(*(server.serve() for server in servers))

    asyncio.run(serve())
