# Mock products

For Docker Compose or a complete local launch of all six servers, see
[the shared startup guide](../docs/RUNNING.md).
`SERVICE_HOST` controls the listening address (loopback by default).
`MOCK_DATA_DIR` optionally moves SQLite files into an existing writable directory;
Compose uses `/data` with a separate named volume for each product.

Two fake products that play our customers' role. Each is only what a real product would hand
us: an HTTP API, an API key and a text context. The [execution server](../execution/README.md)
connects to them through [products.toml](../execution/products.toml). Each also has its own
customer portal, so changes the agent makes show up live during a demo.

| Product | What | API + portal | Context |
|---|---|---|---|
| `cloudbox` | cloud storage subscription (same domain as the `CLOUDBOX` manifest) | http://127.0.0.1:9201 | [cloudbox/context.md](cloudbox/context.md) |
| `shopx` | online store (the manifest spec's e-commerce example) | http://127.0.0.1:9202 | [shopx/context.md](shopx/context.md) |

## Run

From the repository root, with the execution server's virtualenv (or
`pip install -r mocks/requirements-dev.txt`):

```bash
python -m mocks.cloudbox      # add --reset to rebuild the demo data
python -m mocks.shopx
```

Open the URL, pick a demo customer and sign in; the page refreshes every 3 seconds.

API keys default to `cloudbox-dev-key` and `shopx-dev-key` (override with `CLOUDBOX_API_KEY`,
`SHOPX_API_KEY`). The API answers `Authorization: Bearer <key>` plus `X-Customer-Id`, or the
portal's demo login cookie, which is a mock and has no passwords. Another customer's record
answers 404, like a missing one.

## Demo data

| Customer | Product | Situation |
|---|---|---|
| `c-101` Олена Коваль | cloudbox | paid for Plus (`pay-501`), payment never applied, still on Free |
| `c-102` Андрій Мельник | cloudbox | Pro with auto-renewal on |
| `c-103` Ірина Бондар | cloudbox | charged twice for the same month of Plus (`pay-503`, `pay-504`) |
| `s-201` Олена Коваль | shopx | `1042` processing, `1043` delivered, `1044` shipped |
| `s-202` Максим Ткаченко | shopx | `2001` processing; never visible to `s-201` |

## How a mock is built

- `context.md` is the only description we get. Its ```` ```sql ```` block **is** the database:
  on first start [common.py](common.py) creates `<name>.sqlite3` from it and loads `seed.sql`.
  The schema the agent reads and the one the product runs on cannot drift apart.
- `app.py` is the Starlette API from the context's API table, plus the portal routes.
- `portal.html` is the product's own customer page, plain HTML and JS.
- Every portal also signs tokens for our support widget at `POST /support/token`
  (secret `<NAME>_WIDGET_SECRET`, default `<name>-widget-dev-secret`); see
  [../widget/DESIGN.md](../widget/DESIGN.md). The CloudBox portal embeds the widget.

Adding a product: copy a folder, rewrite those four files, add a `__main__.py` port and an
entry in `execution/products.toml`.

Tests: `cd mocks && pytest && ruff check . && ruff format --check .`
