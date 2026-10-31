"""Client for our backend (the future McpGateway): act as a customer, then apply verdicts.

Synchronous, one connection per call, so Django code can use it directly (not from inside a
running event loop).

    client = ExecutionClient("http://127.0.0.1:9000", service_key)
    token = sign("shopx", "s-201")                 # from the session, never from the model
    client.read(token, "/orders/1042")             # {"http_status": 200, "data": {...}}
    proposal = client.propose(token, "POST", "/orders/1042/cancel", "Cancel order 1042")
    client.proposal(proposal["proposal_id"])       # what reviewers look at
    client.execute(proposal["proposal_id"])        # once Critic, Policy and whoever confirms agree
"""

import asyncio
import json
from typing import Any

import httpx2

try:
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
except (ImportError, ModuleNotFoundError):
    Client = None
    streamable_http_client = None

from .identity import TOKEN_HEADER


class ExecutionError(Exception):
    pass


class ExecutionClient:
    def __init__(self, url: str, service_key: str):
        self.url = url.rstrip("/")
        self._service = {"Authorization": f"Bearer {service_key}"}

    # As the customer, over MCP: exactly what the model can do.

    def context(self, token: str) -> str:
        return self._tool(token, "get_product_context", {})

    def read(self, token: str, path: str) -> dict:
        return self._tool(token, "read", {"path": path})

    def propose(
        self, token: str, method: str, path: str, summary: str, body: dict | None = None
    ) -> dict:
        args = {"method": method, "path": path, "summary": summary, "body": body}
        return self._tool(token, "propose_call", args)

    # As our backend, over HTTP: what the model can never do.

    def proposal(self, proposal_id: str) -> dict:
        return self._http("GET", f"/proposals/{proposal_id}")

    def execute(self, proposal_id: str) -> dict:
        """Run it once. The result's status is "executed" or "failed" (see result.http_status)."""
        return self._http("POST", f"/proposals/{proposal_id}/execute")

    def reject(self, proposal_id: str) -> dict:
        return self._http("POST", f"/proposals/{proposal_id}/reject")

    def _tool(self, token: str, name: str, args: dict) -> Any:
        if Client is None or streamable_http_client is None:
            raise ExecutionError("mcp package is not installed")

        async def call():
            async with httpx2.AsyncClient(headers={TOKEN_HEADER: token}, timeout=15) as http:
                transport = streamable_http_client(f"{self.url}/mcp", http_client=http)
                async with Client(transport) as mcp:
                    return await mcp.call_tool(name, args)

        result = asyncio.run(call())
        text = result.content[0].text if result.content else ""
        if result.is_error:
            raise ExecutionError(text)
        if result.structured_content is not None:
            content = result.structured_content
            return content["result"] if set(content) == {"result"} else content
        try:
            return json.loads(text)
        except ValueError:
            return text

    def _http(self, method: str, path: str) -> dict:
        response = httpx2.request(method, self.url + path, headers=self._service, timeout=15)
        if response.status_code >= 400:
            raise ExecutionError(response.json().get("detail", response.text))
        return response.json()
