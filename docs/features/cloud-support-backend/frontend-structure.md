# Frontend structure

The inspected frontend is the original React/TypeScript scaffold, not a customer-support UI.

| Source / symbol | Actual behavior |
| --- | --- |
| [App.tsx](../../../frontend/src/App.tsx), `App` (`ui-health`) | On mount, `api.get('/health/')`; renders `checking…`, returned status or `unreachable`. No router or product screens. |
| [client.ts](../../../frontend/src/api/client.ts), `apiFetch` (`browser-api`) | Prefixes `/api`, includes cookies, uses JSON, reads `csrftoken` for unsafe requests and sends `X-CSRFToken`; returns null for 204, throws `ApiError` for non-OK responses. |
| [client.ts](../../../frontend/src/api/client.ts), `api` / `ApiError` | GET/POST/PATCH/DELETE wrappers; status and raw parsed error body are available. Only GET health is called by the screen. |
| [vite.config.ts](../../../frontend/vite.config.ts), `defineConfig` | Development proxy for `/api`, `/admin`, `/static`; `BACKEND_URL` selects target. This is not evidence of production hosting configuration. |
| [App.test.tsx](../../../frontend/src/App.test.tsx) | Scaffold UI test; not evidence of customer/operator feature coverage or a successful run. |

Authentication screens, billing dashboard, transcript polling, confirmation controls, waiting/operator states, staff console, business API types and subscription refresh are **Not applicable to the current frontend implementation: these layers have not been built**. Their required product behavior remains planned in AGENTS.md.

The reusable client is compatible with a same-origin session/CSRF flow, but does not initiate login or automatically bootstrap `/auth/csrf/`. The current health GET can bootstrap the cookie; a future login flow must use the latest cookie after rotation. `ApiError` stores the error envelope but does not render field-level or localized messages itself.

No frontend-to-database activation or cancellation path exists. There is no current UI evidence of loading/error/confirmation handling beyond the health screen. Frontend build and tests were not run for this documentation change.
