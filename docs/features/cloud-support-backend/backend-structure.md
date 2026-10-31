# Backend structure

## Route registration and HTTP contract

[config/urls.py](../../../backend/config/urls.py) includes `apps.core.urls` and `apps.support.urls` under `/api/`; it also retains standard Django `/admin/`. The admin is not the product operator console; no project model admin registration is present.

Registered business routes are in [support/urls.py](../../../backend/apps/support/urls.py). UUID converters apply to resource IDs. All paths have trailing slashes. API IDs below are indexed in [entry-points.json](entry-points.json).

| Entry ID | Method and full path | Input -> output / access |
| --- | --- | --- |
| `health` | GET `/api/health/` | Public; `{status: "ok"}` and CSRF cookie; not a DB/provider readiness check |
| `csrf-bootstrap` | GET `/api/auth/csrf/` | Public; CSRF cookie and detail |
| `session-login` | POST `/api/auth/login/` | `{username,password}` -> `{id,username,is_staff}`; explicit login CSRF; generic 403 for bad credentials |
| `session-logout` | POST `/api/auth/logout/` | Empty object ->204; authenticated |
| `current-user` | GET `/api/me/` | Session -> `{id,username,is_staff}` |
| `subscription-read` | GET `/api/subscription/` | Owner -> SubscriptionSerializer; 404 if none |
| `conversation-create` | POST `/api/conversations/` | Empty object ->201 conversation detail |
| `conversation-read` | GET `/api/conversations/<uuid:conversation_id>/` | Owner -> conversation detail; foreign/missing ->404 |
| `customer-message` | POST `/api/conversations/<uuid:conversation_id>/messages/` | `{text,client_message_id}` -> ChatResult; current fallback hands off AI-mode cases |
| `cancel-confirm` | POST `/api/actions/<uuid:action_id>/confirm/` | Empty object -> `{action,subscription,subscription_changed}`; owner; cancellation only |
| `operator-queue` | GET `/api/operator/conversations/` | Staff -> `{results:[{id,status,summary,version,assigned_operator_id,created_at}]}` for waiting/operator cases |
| `operator-read` | GET `/api/operator/conversations/<uuid:conversation_id>/` | Staff -> detail for waiting/operator/resolved; denies a different assignee with 403 |
| `operator-claim` | POST `/api/operator/conversations/<uuid:conversation_id>/claim/` | Staff, empty object -> detail; other claim/state ->409 |
| `operator-reply` | POST `/api/operator/conversations/<uuid:conversation_id>/messages/` | Assigned staff, message input ->201 message; identical retry ->200 |
| `operator-resolve` | POST `/api/operator/conversations/<uuid:conversation_id>/resolve/` | Assigned staff, empty object -> detail; repeated resolve is harmless |

The additional operator detail GET extends the initial AGENTS.md table using the same conversation-detail serializer. No public payments/propose/synchronize/refund endpoint exists. Standard framework OPTIONS/HEAD behavior is not catalogued as a separate product action.

## Schemas and errors

[support/serializers.py](../../../backend/apps/support/serializers.py) defines:

- `StrictSerializer`: JSON object only; unknown input keys rejected.
- `MessageInput`: nonblank text up to 4000 characters and client ID up to 128; `EmptyInput` accepts no fields. `accounts.views.LoginInput` limits username to 150/password to 256 and preserves password whitespace.
- `SubscriptionSerializer`: id, nested plan `{id,name,storage_limit_gb}`, status, period_end, auto_renew, version. Price is not in this public response.
- `MessageSerializer`: id, sender, text, created_at; internal sender_user, client ID and response cache are omitted.
- `ActionSerializer`: id, kind, status, Ukrainian description, expires_at; no mutable approval/parameters or raw result in this response.
- `ConversationSerializer`: id, status, version, summary, messages, pending_action. It selects newest unexpired awaiting-confirmation action only in `ai`, without checking current subscription version.

Current HTTP ChatResult has conversation_id, persisted conversation_status, null reply, null pending_action and subscription_changed=false. It is stored in Message.response for retries.

[core/errors.py](../../../backend/apps/core/errors.py) implements `Conflict` (409, state_conflict), DRF error wrapping `{error:{code,message,fields?}}`, and a separate Django CSRF failure JSON response. Session authentication is configured without a challenge, so unauthenticated protected requests are expected to return 403, not 401. CSRF errors inside DRF use its permission-denial path; the Django CSRF failure view uses `csrf_failed`. Unexpected exceptions and unmatched URLs are not guaranteed this envelope. No throttle class/rate or explicit 429/503 provider branch is configured.

## Domain services, transactions and concurrency

[support/services.py](../../../backend/apps/support/services.py) contains the actual services, including the wrappers `propose_sync_subscription` and `propose_cancel_auto_renewal`. Functions accept the trusted user as Python context, not a client/model-selected user ID.

`begin_turn`, `finish_turn`, `handoff_to_operator`, `propose_action`, `record_review` and `_execute` are atomic. Mutation lock order is conversation -> subscription -> payment -> action where applicable. `check_turn` requires ai status, matching version/token and a lease younger than 45 seconds. Synchronization replays successful Action rows before stale-state checks as a read-only result. Proposals use a ten-minute expiry. Successful writes go directly to `succeeded`; the declared `executing` status is not used.

Review validates exactly decision/reason/missing_fields, decision in allow/ask_user/handoff, nonempty reason <=1000 characters and a list of string fields. Repeat review, stale turn and expiry conflict. It stores rejected for non-allow or any missing information, and awaiting_confirmation for an allowed cancellation. There is no actual provider/critic verification inside this service.

Message deduplication combines transaction checks and `unique_client_message`. Lease recovery can reuse an unfinished Message row. `idempotency_key` is server-generated and unique; clients do not submit it. No worker/outbox/external adapter exists.

## Configuration and tests

[settings.py](../../../backend/config/settings.py) reads `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` and optional `DATABASE_URL`. SQLite is the existing default (`IMMEDIATE`, timeout 5); DATABASE_URL uses django-environ. PostgreSQL driver dependencies are in [requirements-postgres.txt](../../../backend/requirements-postgres.txt). Time zone is UTC, `USE_TZ=True`; no model ID/timeouts/step budgets are configured yet. `seed_demo` separately reads `DEMO_PASSWORD` from the process environment.

| Test source | Intended checks, not observed passing results |
| --- | --- |
| [test_health.py](../../../backend/apps/core/tests/test_health.py) | Health response and CSRF cookie |
| [test_backend.py](../../../backend/apps/support/tests/test_backend.py) | Exact entitlement/replay, failed/pending/foreign/out-of-period/superseded payments, foreign conversation/action denial, cancellation confirmation/staleness/expiry, malformed/missing critic data, handoff invalidation, lease conflict/recovery, duplicate messages, injection text on the no-provider fallback, staff permissions and login CSRF, seed preservation |
| [test_concurrency.py](../../../backend/apps/support/tests/test_concurrency.py) | Two independent PostgreSQL connections: apply the same Action once; exclusive operator claim. Skipped on other database vendors. |

The injection test exercises customer text on a path that never calls a model; it does not establish real actor/critic prompt-injection resistance. Provider timeout/malformed network response tests cannot exist for the absent adapter. Runtime, migration drift and database behavior remain **Not verified** in this documentation task.
