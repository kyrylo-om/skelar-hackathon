# End-to-end flow

Entry IDs refer to [entry-points.json](entry-points.json); rules refer to [business-context.md](business-context.md). All sequences are traced from code; runtime execution is **Not verified**.

## Authentication and reads

1. A browser or API client calls `csrf-bootstrap` (or `health`). The public GET ensures a CSRF cookie (BR-02). The current `ui-health` component calls only health.
2. `session-login` validates username/password and calls Django `authenticate` and session login under explicit CSRF protection. Read the rotated CSRF cookie for the next write (BR-01–03).
3. `current-user`, `subscription-read` and `conversation-read` use the authenticated session. Subscription absence or a foreign resource returns 404. `session-logout` accepts an empty object and returns 204.

## Currently wired customer-to-operator path

| Step | Entry ID / actor | Validation, persistence and result |
| --- | --- | --- |
| Create conversation | `conversation-create`, customer | Empty input, session owner, new `ai` conversation; 201 |
| Submit message | `customer-message`, customer | `MessageInput`, then `turn-begin`; reject resolved state/new work during active lease; save customer text once (BR-03, BR-09, BR-12) |
| Retry existing ID | `turn-begin`, then `customer-message` | Different text ->409; completed response reused with current conversation status and pending action hidden outside `ai`; incomplete work may recover after lease expiry |
| Provider unavailable | `human-handoff`, called by `customer-message` | No actor/critic/network request is attempted; token/version checked; deterministic summary, `waiting_operator`, version increment, lease cleared, pending actions rejected (BR-10) |
| Return chat result | `customer-message` | Separate short transaction locks conversation and stores response on Message; `reply=null`, `pending_action=null`, `subscription_changed=false` |
| Queue/detail/claim | `operator-queue`, `operator-read`, `operator-claim`, staff | Waiting and assigned cases appear in queue; transactional exclusive assignment moves waiting case to `operator` (BR-11) |
| Continue same transcript | `operator-reply`, assigned staff; `customer-message`, customer | Operator reply is persisted; customer messages keep entering the same conversation without an AI token; customer reads transcript through `conversation-read` |
| Resolve | `operator-resolve`, assigned staff | `operator -> resolved`, version increments once; repeated resolve returns detail; new customer messages then conflict |

## Internal paid-plan synchronization path

Preconditions: an authenticated user context, subscription, eligible server payment, conversation in `ai`, and a token/version issued by `turn-begin`. There is no HTTP caller for this complete path yet.

1. `sync-propose` -> `action-propose` locks conversation, subscription and payment, checks BR-04 and creates a ten-minute `proposed` Action with evidence/version snapshots.
2. Future orchestration must collect a critic result outside DB transactions. `critic-review` validates exact keys and server turn freshness (BR-06). Non-allow or missing fields persist `rejected`; clarification/handoff is the caller's job.
3. `sync-execute` -> `action-execute` rechecks state/ownership/approval/eligibility under locks. It writes payment `applied_at`, payment plan/period end to subscription, `status=active`, increments subscription version and records `succeeded`/result atomically (BR-05). It does not change `auto_renew`.
4. A repeated successful action returns the current subscription with `changed=false`, including after handoff; it does not write a new entitlement.
5. `turn-finish` can store a bounded assistant reply and release the lease. Future integration must store the matching ChatResult atomically with finalization; this is not currently wired.

## Cancellation proposal and confirmation

1. `cancel-propose` -> `action-propose` requires renewal enabled, captures subscription version and creates `proposed` without changing billing state.
2. `critic-review` allow with empty missing fields changes it to `awaiting_confirmation`; other reviews reject it. `turn-finish` clears the active lease.
3. `conversation-read` can expose the newest unexpired awaiting-confirmation action while conversation status is `ai`. The product confirmation UI is absent.
4. Customer invokes `cancel-confirm` with `{}`. `cancel-execute` -> `action-execute` requires the owner's cancellation Action, live expiry, allow review, matching subscription version, `ai` state and no active token (BR-07–08).
5. Only renewal changes to false, version increases and successful result persists atomically. Replay returns `changed=false`. Stale/expired proposals return 409; no fresh proposal is automatically created.

## State and transaction boundaries

Conversation transitions used by callers: `ai -> waiting_operator -> operator -> resolved`. Token-sensitive domain calls reject work after handoff or a newer turn. No reopen/reassignment endpoint exists. Waiting/operator messages do not invoke AI.

Each service decorated with `transaction.atomic` is a short synchronous unit; handoff and HTTP response persistence are separate units. There are no jobs, workers, WebSockets, Celery tasks or provider network calls. Provider timeout behavior is planned, not demonstrated by the unavailable-provider fallback. See [known-gotchas.md](known-gotchas.md) for finalization and stale-confirmation gaps.
