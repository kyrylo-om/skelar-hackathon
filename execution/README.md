# Execution server

For Docker Compose or a complete local launch of all six servers, see
[the shared startup guide](../docs/RUNNING.md).
`SERVICE_HOST` controls the listening address (loopback by default).
`EXECUTION_ALLOWED_HOSTS` is a comma-separated MCP Host allowlist; Compose explicitly adds
`execution:9000` while preserving DNS rebinding protection.

Our MCP server, and the only way from the support agent to a connected product. It knows nothing
about any particular product: a product hands us an HTTP API, an API key and a text context
(what it is, its support rules, its API, its database schema). An OpenAPI spec is never required,
and products give us no risk levels. Whether an action may run is decided on our side by the
independent reviewers in `backend/apps/security` (Critic, Policy, a human) before anyone calls
execute.

```
agent / orchestrator ──MCP──► execution server ──HTTP (API key + X-Customer-Id)──► product API
  (customer token)              read: runs now
                                propose_call: stored, NOT run
our backend ──HTTP (service key)──► /proposals/{id}/execute  (after review)
```

## Run

```bash
python3 -m venv execution/.venv && source execution/.venv/bin/activate
pip install -r execution/requirements-dev.txt
export EXECUTION_SECRET=change-me             # signs customer tokens; shared with our backend
export EXECUTION_SERVICE_KEY=change-me-too    # our backend's key for the proposal endpoints
export CLOUDBOX_API_KEY=cloudbox-dev-key SHOPX_API_KEY=shopx-dev-key   # products' keys
python -m execution                           # MCP at http://127.0.0.1:9000/mcp
```

Run the mock products next to it (see [../mocks/README.md](../mocks/README.md)). Connected products
are listed in [products.toml](products.toml) (or `EXECUTION_PRODUCTS`). The server will not start
without its secrets or a product's key.

Tests (they use the mocks in process):

```bash
cd execution && pytest && ruff check . && ruff format --check .
```

## Identity

Every MCP request carries `X-Customer-Token`, signed by our backend for the logged-in session:
`<tenant>.<customer_id>.<expires>.<hmac>`, where `tenant` is the product's key in
`products.toml` and `customer_id` is the customer's id **in that product**.
`execution.identity.sign(tenant, customer_id)` makes one, and `python -m execution.mint shopx s-201`
prints one for manual testing. No tool takes a product or a customer, so the model cannot choose
whose data it touches. The product sees our API key and `X-Customer-Id` and scopes everything
to that customer.

## MCP tools (what the model can do)

| Tool | Does |
|---|---|
| `get_product_context()` | the product's context text, as the product wrote it |
| `read(path)` | `GET path` as the customer; returns `{"http_status", "data"}` (a 404 also means "not yours") |
| `propose_call(method, path, summary, body?)` | records `POST/PUT/PATCH/DELETE path` with `body`; returns `proposal_id`. **Never runs it.** |

Paths must be plain paths on the product's API: no other host, no `..`.

## Proposal endpoints (what only our backend can do)

All need `Authorization: Bearer $EXECUTION_SERVICE_KEY`.

| Endpoint | Does |
|---|---|
| `GET /proposals/{id}` | tenant, customer, method, path, body, summary, status, result: exactly what would run |
| `POST /proposals/{id}/execute` | runs it once, as the customer who proposed it. `status` becomes `executed` or `failed`; `result` has the product's `http_status` and `body` |
| `POST /proposals/{id}/reject` | it can never run |

A proposal runs at most once. A second execute, or an execute after reject or expiry
(`EXECUTION_PROPOSAL_TTL`, default 3600 s), answers 409. Proposals live in memory, so a restart
drops pending ones. Every tool call and endpoint call goes to the JSONL audit log
(`EXECUTION_AUDIT_LOG`, default `audit.jsonl`).

## The orchestrator on top (`ORCHESTRATOR_GATEWAY=mcp`)

The backend drives the product through
[backend/apps/orchestrator/mcp_gateway.py](../backend/apps/orchestrator/mcp_gateway.py), an
`McpGateway` with the same interface as the built-in `DevDomainGateway`:

1. **Facts** for Actor, Critic and Policy come from `read("/subscription")` and `read("/payments")`
   as the session's customer. If the product is down or the account is not connected, the chat
   goes to a human.
2. **After Gate says `execute`**, the action is proposed (`method`, `path`, `body` from the
   gateway's `CALLS` table, the future manifest `executor`), then executed.
   - `executed` → reply from the product's real answer.
   - `failed` → honest reply, and the chat goes to a human.
3. **`confirm: customer` actions** (cancelling auto-renewal) are only proposed. The chat shows the
   usual confirm button, and only the customer's own `POST /api/actions/{id}/confirm/` executes
   them, once, and never after the chat went to a human.
4. **Operator approvals** re-check Policy with fresh facts from the product, then propose and
   execute.

Run it all (each in its own terminal, from the repository root, with the variables from "Run"):

```bash
python -m mocks.cloudbox
python -m execution
cd backend && ORCHESTRATOR_GATEWAY=mcp EXECUTION_SECRET=change-me EXECUTION_SERVICE_KEY=change-me-too \
    python manage.py runserver
```

The seed_demo accounts map to CloudBox customers through `EXECUTION_CUSTOMERS` (default
`paid_plus=c-101,active_pro=c-102,refund_review=c-103`). Sign in to the chat as `paid_plus` and
write «Оплатив Plus, а тариф досі Free»: the CloudBox portal (http://127.0.0.1:9201) switches
to Plus.

[client.py](client.py) is the same contract for anything outside Django. An LLM agent with MCP
tool use can also connect directly with a customer token. It can read and propose, but nothing it
proposes runs until our backend executes it.

Not covered yet: undo, other product auth schemes (only Bearer key + `X-Customer-Id`), and
persistence of pending proposals.
