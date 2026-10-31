# Per-app responsibility

There is one backend deployment: Django via `backend/config/wsgi.py` or `asgi.py`. The following are logical Django/Python modules, not separate network services. Human role boundaries follow the supplied AGENTS.md; no unconfirmed individual owner is assigned here.

| Module | Responsibility and authority | Inputs / outputs and dependencies |
| --- | --- | --- |
| `backend/config` | Backend-owned shared settings and root routes, database selection, auth defaults and error handler registration | Environment variable names -> Django configuration; includes `apps.core.urls`, `apps.support.urls` |
| `apps.core` | Public health/CSRF-cookie response and shared error envelope; no domain data ownership | GET health -> status; exceptions -> error response; used by support services/views |
| `apps.accounts` | Authenticate/logout session and expose current user; relies on Django's auth user/session storage | Validated credentials, CSRF/session -> user shape or denial; imports `StrictSerializer`/`EmptyInput` from support |
| `apps.subscriptions` | Authoritative Plan, Subscription and Payment declarations/migrations | Backend domain services read/lock/write these models; no independent public mutation views |
| `apps.support.models` | Conversation, Message and Action persistence | Ownership, state/version/lease, transcript, approval and result records |
| `apps.support.serializers` | Strict request schemas and public response shapes | Views use serializers; Action data is never exposed as a writable state machine |
| `apps.support.services` | Trusted mutation boundary, proposals/review validation, execution, lease management and deterministic handoff | Injected user/token/version -> scoped reads, candidates, persisted effects/conflicts; calls ORM, no provider |
| `apps.support.views` / `urls` | Customer and staff HTTP boundary | Session/permissions and validated payload -> service calls/transactions and REST responses |
| `apps.support.management.commands.seed_demo` | Local synthetic fixture setup, preserves existing demo state | DEBUG and locally supplied password -> users/plans/subscriptions/payments in one transaction |
| `frontend` | Separate React/Vite app; currently health-only screen and shared fetch wrapper | Calls health; proxy/cookies/CSRF plumbing exists, product flows absent |

## AI boundary

Actor, critic and provider modules do not exist in the inspected tree. The planned AI developer owns provider orchestration and typed allowlisted tool wrappers. Backend owns shared models/migrations and domain authorization. A model must not receive the authority to select a different session user or manufacture a confirmation/review. `record_review` validates a supplied review; it does not call or authenticate an external critic.

`confirm_cancellation` belongs to the authenticated confirmation endpoint, not the model tool set. Trusted system/customer handoff may omit the lease token; future AI callbacks must pass it. The generic `propose_action` and `_execute` are internal service helpers, not arbitrary HTTP endpoints.

## Ownership overlap to coordinate

AI integration will need to replace the unavailable-provider boundary in `support.views.messages` and atomically persist the final ChatResult. This touches backend-owned views and Message.response; agree that change with the backend role. `accounts` currently depends on request serializers in `support`, and the domain services depend on response serializers there. These are actual shared Python dependencies, not independent deployable APIs.
