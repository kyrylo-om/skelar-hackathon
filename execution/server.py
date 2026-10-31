"""Our execution server: the only way from the support agent to a connected product.

The model (over MCP) can only look and propose:
  get_product_context()        the product's own text: what it is, rules, API, database schema
  read(path)                   GET on the product's API as the current customer
  propose_call(method, ...)    record a state-changing call; it does NOT run

Our backend (over HTTP, with EXECUTION_SERVICE_KEY) decides, after independent review:
  GET  /proposals/{id}          exactly what would run, for the Critic, Policy or an operator
  POST /proposals/{id}/execute  run it once, as the customer it was proposed for
  POST /proposals/{id}/reject   make sure it never runs

Product and customer come from the signed X-Customer-Token (identity.py), never from arguments.
Every call is audited (audit.py).
"""

import hmac
import json
import os
from typing import Annotated, Any, Literal

import httpx2
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import audit
from .identity import TOKEN_HEADER, IdentityError, verify
from .products import Product, call, check_path
from .proposals import EXECUTED, FAILED, Proposals

MAX_BODY = 10_000
INSTRUCTIONS = (
    "You help the customer of one product. Start with get_product_context: it describes the "
    "product, its support rules, its API and its database schema. Use read to look up the "
    "customer's data; every call already acts as this customer, so paths never name a customer. "
    "To change anything, use propose_call. A proposal is NOT executed: independent reviewers "
    "decide, and the customer or a human may have to confirm. Never tell the customer that a "
    "proposed change is done."
)


def create_server(products: dict[str, Product], proposals: Proposals | None = None) -> MCPServer:
    server = MCPServer("execution", instructions=INSTRUCTIONS)
    proposals = proposals or Proposals()

    def session(ctx: Context, event: str) -> tuple[Product, str]:
        try:
            tenant, customer = verify((ctx.headers or {}).get(TOKEN_HEADER))
        except IdentityError as exc:
            audit.write(event, None, None, audit.DENIED, detail=str(exc))
            raise ToolError("Could not identify the customer") from exc
        if tenant not in products:
            audit.write(event, tenant, customer, audit.DENIED, detail="unknown product")
            raise ToolError("This product is not connected")
        return products[tenant], customer

    def valid_path(path: str, event: str, product: Product, customer: str) -> str:
        try:
            return check_path(path)
        except ValueError as exc:
            audit.write(event, product.name, customer, audit.DENIED, path=path, detail=str(exc))
            raise ToolError(str(exc)) from exc

    @server.tool()
    async def get_product_context(ctx: Context) -> str:
        """The product's own description: what it is, support rules, API and database schema."""
        product, customer = session(ctx, "context")
        audit.write("context", product.name, customer, audit.OK)
        return product.context

    @server.tool()
    async def read(path: str, ctx: Context) -> dict[str, Any]:
        """GET a path of the product's API as the current customer, e.g. "/orders/1042".

        Returns {"http_status": ..., "data": ...}; a 404 also means "not this customer's".
        """
        product, customer = session(ctx, "read")
        valid_path(path, "read", product, customer)
        try:
            status, data = await call(product, customer, "GET", path)
        except httpx2.HTTPError as exc:
            audit.write("read", product.name, customer, audit.FAILED, path=path, detail=str(exc))
            raise ToolError("The product is not reachable") from exc
        outcome = audit.OK if status < 400 else audit.FAILED
        audit.write("read", product.name, customer, outcome, path=path, http_status=status)
        return {"http_status": status, "data": data}

    @server.tool()
    async def propose_call(
        method: Literal["POST", "PUT", "PATCH", "DELETE"],
        path: str,
        summary: Annotated[str, Field(min_length=1, max_length=300)],
        ctx: Context,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Propose one state-changing call to the product's API. It is NOT executed now.

        summary: one sentence a human reviewer and the customer will read, e.g.
        "Cancel order 1042". Independent reviewers decide whether it runs.
        """
        product, customer = session(ctx, "propose")
        valid_path(path, "propose", product, customer)
        if len(json.dumps(body, ensure_ascii=False)) > MAX_BODY:
            audit.write("propose", product.name, customer, audit.DENIED, detail="body too large")
            raise ToolError("body is too large")
        proposal = proposals.create(product.name, customer, method, path, body, summary)
        audit.write(
            "propose",
            product.name,
            customer,
            audit.OK,
            proposal=proposal.id,
            method=method,
            path=path,
            body=body,
            summary=summary,
        )
        return {
            "proposal_id": proposal.id,
            "status": "proposed",
            "note": "Not executed. It runs only if our reviewers approve it.",
        }

    def is_service(request: Request) -> bool:
        key = os.environ.get("EXECUTION_SERVICE_KEY")
        given = request.headers.get("authorization", "")
        return bool(key) and hmac.compare_digest(given, f"Bearer {key}")

    def refuse(request: Request) -> JSONResponse | None:
        if not is_service(request):
            audit.write("service", None, None, audit.DENIED, path=request.url.path)
            return JSONResponse({"detail": "Unauthorized"}, 401)
        if proposals.get(request.path_params["proposal_id"]) is None:
            return JSONResponse({"detail": "Unknown proposal"}, 404)
        return None

    @server.custom_route("/proposals/{proposal_id}", methods=["GET"])
    async def show(request: Request) -> JSONResponse:
        if refused := refuse(request):
            return refused
        return JSONResponse(proposals.get(request.path_params["proposal_id"]).public())

    @server.custom_route("/proposals/{proposal_id}/execute", methods=["POST"])
    async def execute(request: Request) -> JSONResponse:
        if refused := refuse(request):
            return refused
        proposal = proposals.claim(request.path_params["proposal_id"])
        if proposal is None:
            current = proposals.get(request.path_params["proposal_id"]).state()
            return JSONResponse({"detail": f"Proposal is {current}"}, 409)
        product = products[proposal.tenant]
        try:
            status, data = await call(
                product, proposal.customer, proposal.method, proposal.path, proposal.body
            )
        except httpx2.HTTPError as exc:
            status, data = None, {"detail": f"The product is not reachable: {exc}"}
        proposal.status = EXECUTED if status is not None and status < 400 else FAILED
        proposal.result = {"http_status": status, "body": data}
        audit.write(
            "execute",
            proposal.tenant,
            proposal.customer,
            audit.OK if proposal.status == EXECUTED else audit.FAILED,
            proposal=proposal.id,
            method=proposal.method,
            path=proposal.path,
            http_status=status,
        )
        return JSONResponse(proposal.public())

    @server.custom_route("/proposals/{proposal_id}/reject", methods=["POST"])
    async def reject(request: Request) -> JSONResponse:
        if refused := refuse(request):
            return refused
        proposal = proposals.reject(request.path_params["proposal_id"])
        if proposal is None:
            current = proposals.get(request.path_params["proposal_id"]).state()
            return JSONResponse({"detail": f"Proposal is {current}"}, 409)
        audit.write("reject", proposal.tenant, proposal.customer, audit.OK, proposal=proposal.id)
        return JSONResponse(proposal.public())

    return server
