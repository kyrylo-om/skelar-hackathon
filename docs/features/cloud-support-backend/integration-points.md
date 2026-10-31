# Integration points

This bundle spans the current backend modules; separate feature bundles for auth, billing, conversation and operators do not yet exist. Their logical boundaries are described here without links to absent documents.

| Direction / interface | Payload, authority and authentication | Failure/retry and evidence |
| --- | --- | --- |
| Browser -> accounts | `/api/auth/csrf/`, `/auth/login/`, `/auth/logout/`, `/me/`; browser cookies and CSRF; Django auth is user authority | Generic credential denial, CSRF rejection, 403 unauthenticated expectation; `accounts/views.py:LoginView`, `logout`, `me`; [route details](backend-structure.md) |
| Browser -> support | Conversation/message/confirmation APIs; session-owned UUID resources; staff permissions for operator APIs | 404 for inaccessible customer data, 409 conflicts, message IDs for dedup; `support/views.py` and `support/serializers.py`; client strips no authorization boundary |
| Frontend -> backend dev server | Vite proxy for `/api`, `/admin`, `/static`; `apiFetch` includes cookies and CSRF header | `ApiError` retains status/body; no built-in business retry or polling; actual screen uses health only; [frontend trace](frontend-structure.md) |
| Accounts -> support serializers | Python imports `StrictSerializer`/`EmptyInput`; no network | Import-time dependency; schema changes affect login/logout; `accounts/views.py` |
| Support domain -> subscription data | Scoped ORM queries and short atomic writes; server Payment determines entitlement; subscription version protects proposal freshness | Payment eligibility/version changes -> Conflict; same successful Action -> unchanged replay; `support/services.py:propose_action`, `_execute` |
| Support domain -> public response schema | `SubscriptionSerializer` builds read and persisted successful Action result | Changing public subscription shape also changes future saved result snapshots; `support/services.py:get_subscription`, `_execute` |
| Customer message -> operator queue | `handoff_to_operator` stores summary/status and rejects pending candidates; authenticated owner or trusted system context | Current message handler always uses provider-unavailable fallback for AI-mode requests; no external dependency needed; `support/views.py:messages` |
| Future AI -> domain | Python services with injected user, server turn token and version; actor sees only allowlisted tool wrappers; critic result exact keys | Planned network boundary; current services validate data/freshness but do not establish who generated the review; [flow](end-to-end-flow.md) and [trust gaps](known-gotchas.md) |
| Backend -> database | SQLite default or DATABASE_URL PostgreSQL; model/migration declarations are source of schema | Driver/schema/connectivity and lock behavior Not verified; no production DB or migration status inferred; `config/settings.py`, both initial migrations |
| Local operator -> seed command | `python manage.py seed_demo`, DEBUG and locally chosen DEMO_PASSWORD; no exposed endpoint | CommandError for missing prerequisites; preserves prior records, does not reset; `support/management/commands/seed_demo.py:Command.handle` |
| Django -> auth/session/admin framework | Built-in User/session and admin URL; user IDs are serialized as strings while project resources use UUID | Standard Django capabilities, not a custom signup/reset API or model management console; `config/settings.py`, `config/urls.py` |

Paths abbreviated as `support/...` above live under `backend/apps/support/`; `accounts/...` under `backend/apps/accounts/`.

## Internal AI adapter contract

The following are implemented Python interfaces; they are not independently authenticated HTTP services. Caller must inject session-derived `user`, never model-selected identity. `token` and `version` must come from the server's active turn:

```text
begin_turn(user, conversation_id, text, client_message_id)
get_subscription(user)
get_payments(user)
propose_sync_subscription(user, conversation_id, token, version, payment_id)
propose_cancel_auto_renewal(user, conversation_id, token, version)
record_review(user, action_id, token, version, review)
execute_sync(user, action_id, token, version)
finish_turn(user, conversation_id, token, version, text=None)
handoff_to_operator(user, conversation_id, reason, token=..., version=...)
```

Read payment data includes UUID, Decimal and datetime Python values; future provider adapters must serialize/redact them intentionally. `review` must have exactly decision, reason, missing_fields; valid decision values are allow/ask_user/handoff. Non-allow or missing information rejects the Action; orchestrator must perform clarification/handoff itself. Review must be obtained independently of actor arguments.

`confirm_cancellation(user, action_id)` is reserved for the authenticated endpoint. No actor tool should expose it. Successful execution returns Action, current Subscription and a changed boolean; do not announce mutation success before that persisted result. Pending Action serializers expose only display information; immutable parameters are created by the backend.

## External integrations intentionally absent

Not applicable: no network client, payment/refund provider, storage service, background queue, mail integration, model SDK, live Gemini/Gemma configuration or model tool dispatcher exists in the inspected backend. The model/provider failure paths specified in AGENTS.md are requirements for the future adapter. Health returning ok does not validate any of these services.

Breaking changes to coordinate include JSON field names, error envelope/403 handling, UUID routes, proposal kinds, subscription version semantics, critic schema, lease expiry and transaction ordering. Future payment ingestion must lock the owning Subscription before inserting a superseding purchase to cooperate with synchronization. Future AI finalization must make Message.response and reply/lease finalization atomic. See [prior integration handoff](../../BACKEND.md).
