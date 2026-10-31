# Mock products

Fake products for the support agent to act on. Each product is a fake backend HTTP API plus
its own MCP server. The agent talks only to the MCP servers.

| Product         | MCP server                     | Fake backend            | Tools |
|-----------------|--------------------------------|-------------------------|-------|
| `shop`          | `http://127.0.0.1:9001/mcp`    | `http://127.0.0.1:9101` | list_orders, get_order, cancel_order*, change_address*, refund* |
| `subscriptions` | `http://127.0.0.1:9002/mcp`    | `http://127.0.0.1:9102` | list_subscriptions, get_subscription, pause_subscription*, cancel_subscription*, list_invoices, refund_invoice* |

\* needs the customer's confirmation (see below).

Seed data: customer `7` owns shop orders `1042` (processing), `1043` (delivered),
`1044` (shipped), subscription `sub-1` and invoices `inv-501`, `inv-502`.
Customer `8` owns order `2001`, `sub-2` and `inv-601`, which customer `7` must never reach.
State is in memory and resets on restart.

## Run

Tested with Python 3.14.

```bash
cd products
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export SUPPORTKIT_SECRET=change-me      # shared with whoever signs customer tokens
python -m shop                          # or: python -m subscriptions
```

Tests and linting:

```bash
pytest && ruff check . && ruff format --check .
```

## Connecting the agent

Every request to an MCP server must carry `X-Customer-Token`, a token signed for the
logged-in customer. The orchestrator adds this header; the model never sees it, and no tool
takes a customer id, so the model cannot pick whose data it touches.

```python
from supportkit.identity import sign          # or any HMAC-SHA256 of "<id>.<expires>"
token = sign(customer_id)                     # "<customer_id>.<expires_unix>.<hmac_hex>"

async with httpx2.AsyncClient(headers={"X-Customer-Token": token}) as http:
    async with Client(streamable_http_client("http://127.0.0.1:9001/mcp", http_client=http)) as mcp:
        ...
```

For manual testing: `python -m supportkit 7` prints a token for customer 7.

### Confirmations

A tool marked `*` does not run when the model calls it. It returns:

```json
{"status": "confirmation_required", "confirmation_id": "…",
 "summary": "Повернути 30 грн за замовлення №1043", "expires_in": 300}
```

The chat UI shows the summary with a confirm button. When the customer presses it, the
UI (not the model) calls:

```
POST http://127.0.0.1:9001/confirm/<confirmation_id>
X-Customer-Token: <the same customer's token>
```

`200 {"status": "done", "tool": …, "result": …}` means the action ran. `404` means the id is
unknown, expired, already used, or belongs to another customer. `409 {"detail": …}` means a
limit or the backend refused it, with a reason that can be shown to the customer.

## Shared security: `supportkit/`

Products don't implement any of this; it all happens in the kit:

| Module        | What it does |
|---------------|--------------|
| `identity.py` | Verifies the signed `X-Customer-Token`. A missing, forged or expired token is refused. |
| `confirm.py`  | Parks risky calls with their exact arguments. A confirmation is single-use, expires (`SUPPORTKIT_CONFIRM_TTL`, default 300 s) and is bound to its customer. |
| `limits.py`   | Hard caps per tool: `max_amount` on the `amount` argument, and `per_hour` calls per customer (attempts count). |
| `audit.py`    | One JSON line per call to `SUPPORTKIT_AUDIT_LOG` (default `audit.jsonl`): who, which tool, which arguments, outcome `ok`, `pending`, `denied` or `error`. |
| `kit.py`      | `Kit` and `@kit.tool(...)`, which apply all of the above, plus `ApiClient`, the backend client bound to the customer. |
| `backend.py`  | Helpers for fake backends: the caller's id, ownership lookups, JSON errors. |

The fake backends check ownership too, as a real backend would: another customer's record
looks exactly like a missing one.

## Adding a product

Copy `shop/` to `<name>/` and change three files:

- `api.py`: the seed data and the Starlette routes of the fake backend. Use
  `owned(records, request, "<path_param>")` to look a record up, so other customers' records
  stay invisible.
- `server.py`: the tools. Each tool takes `api: ApiClient` first, then its own arguments:

  ```python
  @kit.tool(confirm="Повернути {amount:g} грн за {invoice_id}", max_amount=500, per_hour=3)
  async def refund_invoice(
      api: ApiClient, invoice_id: str, amount: Annotated[float, Field(gt=0)]
  ) -> dict:
      """Refund part or all of an invoice, in UAH."""   # the model reads this
      return await api.post(f"/invoices/{invoice_id}/refund", {"amount": amount})
  ```

  Read-only tools need no options. Anything that changes state gets `confirm=` with a
  customer-facing summary, formatted from the arguments.
- `__main__.py`: two unused ports.

Then add a smoke test to `tests/test_products.py`.
