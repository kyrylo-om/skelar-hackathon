# Support widget

For Docker Compose or a complete local launch of all six servers, see
[the shared startup guide](../docs/RUNNING.md).

The chat a product embeds on its own site with one tag:

```html
<script src="https://<widget host>/widget.js" data-product="cloudbox" data-token-url="/support/token"></script>
```

```
host page (any origin)                         widget origin                 our backend
┌──────────────────────────┐  postMessage   ┌──────────────────┐  Bearer   ┌──────────────────┐
│ widget.js (loader)       │ ─────token───► │ iframe: chat app │ ────────► │ /api/widget/...  │
│  button, iframe          │ ◄─token-req─── │  React           │ ◄── SSE ─ │ apps/widget      │
│  POST data-token-url ──► │                └──────────────────┘           │ → orchestrator   │
│  (host's own backend,    │                                               └──────────────────┘
│   its own cookies)       │
└──────────────────────────┘
```

| Part | What |
|---|---|
| `loader/widget.ts` | Built to `widget.js` (3 KB IIFE, no dependencies). It adds the button in a shadow root, creates the iframe on the first click and fetches tokens from the host. |
| `app/` | The chat UI in the iframe (React + Vite). `api.ts` is the only file that knows the backend endpoints. |
| `shared/protocol.ts` | The postMessage types between the loader and the app. |
| `backend/apps/widget` | Token auth, `GET chat/`, `POST chat/messages/` (SSE) and `POST actions/<id>/confirm/`. |
| `mocks/common.py` | `POST /support/token` on every mock portal: the part each product builds on its side. |

## Decisions

**Identity.** The host's backend signs `<tenant>.<customer_id>.<expires_unix>.<hmac_sha256_hex>` with its own widget secret. This is the `execution/identity.py` format, but signed with a per-product secret rather than our `EXECUTION_SECRET`.
- The backend checks the token against `WIDGET_SECRETS[tenant]` and maps `(tenant, customer)` to a shadow Django user named `widget:<tenant>:<customer>`. Colons can't appear in a normal username, so no regular account can take this name.
- `McpGateway` acts as that tenant and customer.
- The browser never chooses either of them, and `data-product` is only a label.
- With no token, the widget shows "please log in". There are no anonymous visitors.

**Token lifecycle.**
- The token lives 10 minutes (the mock issues it with `expires_in`).
- The app asks the loader for a new one at 80% of its lifetime and once after any 401. If that fails it retries twice (after 1 s and 3 s), then shows "session expired" and keeps the history visible.
- The token is kept in memory only, never in a URL, storage or a log.
- The API calls send no cookies (`credentials: 'omit'`), so the widget doesn't depend on third-party cookies.

**Transport.** `POST /api/widget/chat/messages/ {text}` answers with `text/event-stream`:

| Event | Data |
|---|---|
| `status` | `{stage}`, for now always `"working"` |
| `message` | `{id, role, text, at}`, where role is `customer`, `ai`, `operator` or `system` |
| `done` | `{status}`, the chat status |
| `error` | `{code, message}` |

- Replies arrive whole, never token by token, because the pipeline checks each reply (`reply_is_safe`) before it can be shown.
- `status` is the place for real progress stages once the pipeline exposes them.
- Errors before streaming starts (401, 400) are normal JSON responses.
- `GET /api/widget/chat/` returns the customer's one chat, the same as `/api/review/my/chat/`. It restores history on reload and is polled every 5 s for operator replies.

**Conversation.** Each `(tenant, customer)` has one chat, kept on the server, and the client never holds a conversation ID.

**Confirmation.** Some actions, such as turning off auto-renewal, run only after the customer confirms them.
- The chat payload carries the pending action as `pendingConfirmation: {id, kind, description, expires_at}`, and the widget shows it as a card with a "Підтвердити" button.
- Pressing it calls `POST /api/widget/actions/<id>/confirm/`, which uses the MCP gateway's confirm and all its checks: own action only, not expired, runs once, and never after a handoff.
- Typing "так" in the chat confirms nothing. A confirmed action adds a `system` message to the chat as a record.

**postMessage.**
- Every message carries `channel: 'support-widget'`.
- The loader accepts a message only if `event.origin` is the widget origin and `event.source` is its iframe.
- The app accepts a message only if `event.origin` is the `host` origin the loader put in the iframe URL and `event.source` is `window.parent`.
- Each side sends only to the other's exact origin. The token goes only from the loader to the app.

**Loader UI.**
- The button sits bottom-right, and the panel is 380×600.
- Below 640 px wide, the panel goes full-screen and the button is hidden.
- Esc closes the panel, whether the host page or the iframe has focus. Focus moves into the chat when it opens and back to the button when it closes.
- When the panel is closed, new messages that aren't the customer's own show an unread dot.
- The loader sets the iframe size, so there is no resize protocol.

**Rendering.** Messages are plain text (`white-space: pre-wrap`). There is no `innerHTML` anywhere near content. The loader uses `innerHTML` only for its own static markup.

**Not in v1** (the types leave room for them):
- showing handoff status (`done.status` and `chat.status` already carry it);
- theming;
- checking the host origin on the backend (an allowlist per tenant);
- a public JS API for the host (for example `logout()`, which a page that logs out without reloading would need).

## Known limits

- **The backend serves only CloudBox well.** The orchestrator's manifest is CloudBox-only. A shopx token authenticates and the chat works, but the agent can't read shop data, so it hands the customer to a human. Supporting another product is backend work: a manifest per tenant (see docs/agents/10_ORCHESTRATOR.md).
- **The widget needs the MCP gateway.** It needs `ORCHESTRATOR_GATEWAY=mcp`. In `dev` mode a widget customer has no data in `apps.subscriptions`.
- **One server thread per open stream.** Each reply stream holds a Django thread while the pipeline runs (at most about 30 s). That's fine for a demo. For real traffic use ASGI.

## Run

Each in its own terminal, from the repository root. Use the execution virtualenv for the mocks. Variables:

```bash
export EXECUTION_SECRET=change-me EXECUTION_SERVICE_KEY=change-me-too
export CLOUDBOX_API_KEY=cloudbox-dev-key SHOPX_API_KEY=shopx-dev-key
```

```bash
python -m mocks.cloudbox                                 # host site, http://127.0.0.1:9201
python -m execution                                      # MCP server, :9000
cd backend && ORCHESTRATOR_GATEWAY=mcp \
  WIDGET_SECRETS=cloudbox=cloudbox-widget-dev-secret python manage.py runserver 127.0.0.1:8000
cd widget && npm install && npm run dev                  # widget, http://127.0.0.1:5174
```

Open http://127.0.0.1:9201, sign in as a demo customer and click the chat button.

The widget runs on its own origin (:5174), so the host page always embeds it cross-origin. In dev, Vite proxies `/api/` to Django.

## Build and deploy

`npm run build` writes `dist/`, which is static files only: `widget.js` (fixed name, cache it briefly), `index.html` and hashed `assets/`. Host `dist/` on any static server or CDN.
- If the API is on another origin, build with `VITE_API_BASE=https://api.example.com/api`.
- Add the widget origin to the backend's `CORS_ALLOWED_ORIGINS`.

## Tests

```bash
npm test && npm run lint && npm run build   # unit tests (SSE parsing), lint, types
npx playwright install chromium             # once
npm run e2e                                 # smoke test; starts the whole stack (see playwright.config.ts)
```

The smoke test covers:
- the signed-out state;
- Esc and focus return;
- sign-in on the host and a real reply from the agent;
- no token in the iframe URL and nothing in its storage.

It uses its own backend database in `.e2e/`, but it reuses any servers already running on the same ports.

Backend: `cd backend && pytest apps/widget`.
