# Backend integration handoff

Implemented under `backend/apps/`, preserving the existing scaffold. This is synthetic billing only: no bank, refund provider or storage provisioning is called.

## Current verification status

Implementation and initial migrations are written. Django, DRF and pytest are not installed in the execution environment. Installing `requirements-dev.txt` failed because `pypi.org` DNS resolution is unavailable. Python compilation passed; runtime checks, migrations and test results remain unverified. Existing dependency pins are unchanged. No live AI API call was performed.

## Local setup

Use the existing backend setup in the root README, then:

```bash
cd backend
export SECRET_KEY=local-development-only-secret
export DEBUG=True
export DEMO_PASSWORD=choose-a-local-demo-password
python manage.py migrate
python manage.py seed_demo
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
ruff check .
ruff format --check .
```

Synthetic usernames: `paid_plus`, `active_pro`, `refund_review`, `operator`. All newly created accounts use the locally chosen `DEMO_PASSWORD`. The command requires DEBUG and a password of at least 12 characters. Re-running preserves passwords, paid periods and progressed demo state; it does not reset the database. `paid_plus` starts with Free and a successful unapplied Plus payment. `active_pro` has Pro with renewal enabled. `refund_review` has Plus. `operator` is staff. Prices are illustrative UAH demo rules: Free 5 GB/0, Plus 100 GB/99, Pro 1000 GB/199. Refund eligibility always requires human review.

The existing template and README explicitly selected SQLite; it remains the local default. SQLite uses IMMEDIATE transactions to serialize writes; it does not provide PostgreSQL row-lock semantics. For PostgreSQL:

```bash
pip install -r requirements-postgres.txt
export DATABASE_URL=postgres://cloud_support:local-password@localhost:5432/cloud_support
python manage.py migrate
pytest
```

Use a local test role allowed to create a test database. Two independent-connection concurrency tests (payment application and operator claim) require PostgreSQL and skip on SQLite. Neither database mode has been run in the current environment.

## HTTP contract

The v1 routes in AGENTS.md are registered with UUID resource identifiers, snake_case, trailing slashes, and error envelopes. SessionAuthentication returns **403** for unauthenticated requests (no WWW-Authenticate challenge), CSRF and permission failures; foreign customer resources return 404. Invalid credentials return a generic 403. Input rejects unknown fields. Message text is limited to 4000 characters and client_message_id to 128 characters. Confirm and other empty-body POSTs accept `{}` only. No API accepts mutable Action fields or arbitrary tools.

Bootstrap `GET /api/auth/csrf/`, then send cookies and `X-CSRFToken` on login and subsequent writes. Login rotates the CSRF cookie, so read its new value before the next POST. Login itself enforces CSRF, including for anonymous callers. Keep the Vite same-origin proxy.

One additive integration route is provided because the initial v1 table omitted operator transcript reads: `GET /api/operator/conversations/{id}/`. It returns the existing conversation-detail shape, requires staff, and allows queued cases or the assigned operator's case. Queue includes waiting and assigned conversations, with `assigned_operator_id`; reply/resolve remain assigned-operator-only. Frontend work is untouched.

`POST /conversations/{id}/messages/` currently stores the customer message and transfers to the operator with a deterministic summary when AI would be needed. It returns actual persisted status, null reply and no pending action. This is an explicit provider-unavailable path, **not a mock model response or a completed activation demo**. Further customer messages remain in the same conversation. Duplicate IDs do not append duplicates; reuse with different text returns 409. A crashed turn can be retried after its 45-second lease expires without duplicating the customer message.

## AI developer integration

Do not add public payment mutations. Use `apps.support.services` with the authenticated user injected outside model arguments:

1. `begin_turn(user, conversation_id, text, client_message_id)` returns conversation, persisted message, server token. It rejects overlapping turns with 409 and recovers expired leases. A message with stored `response` is a retry; return it with current conversation status.
2. Run bounded actor/critic calls outside transactions. Read `get_subscription(user)` and `get_payments(user)`; redact context to the minimum needed.
3. Allowlisted adapter functions should call `propose_sync_subscription(user, conversation_id, token, version, payment_id)` or `propose_cancel_auto_renewal(user, conversation_id, token, version)`. These wrap the internal `propose_action` service. The server binds customer, subscription version and payment; models cannot set plan/price/period. Proposal parameters have no update API.
4. Call `record_review(user, action_id, token, version, review)` only after validating the critic response. Its exact keys are `decision`, `reason`, `missing_fields`. Missing fields, ask_user and handoff never authorize execution. Non-allow decisions reject the candidate; the orchestrator must clarify or hand off. No default approval exists. Do not use an actor-provided review as a critic decision.
5. For synchronization, call `execute_sync(user, action_id, token, version)`. It returns action, current subscription, changed. Payment and subscription are locked and persisted with the action atomically. Replay returns the saved success without extending entitlement. All payment ingestion paths must also serialize on the owning subscription before adding superseding purchases.
6. Cancellation with an allow review becomes `awaiting_confirmation`. Return `ActionSerializer` for the customer. Only the authenticated `/actions/{id}/confirm/` endpoint calls `confirm_cancellation`; never expose that function to the actor. It rechecks ownership, expiry, version, critic approval and conversation state. Access/period_end is preserved.
7. `finish_turn(user, conversation_id, token, version, text=None)` validates freshness and stores an optional assistant reply. It clears the lease. The integration must persist the corresponding ChatResult on `Message.response` atomically with finalization, using persisted message/action IDs. Update the current fallback in `support/views.py` when orchestration is ready.
8. `handoff_to_operator(user, conversation_id, reason, token=token, version=version)` pauses AI, invalidates the lease/actions and creates a deterministic summary with subscription facts, customer requests and attempted action results. A trusted customer/system path can omit the token for provider failure or explicit human/refund requests; AI callbacks must pass their token. Never call the actor after handoff. Use Ukrainian customer text and distinguish simulated billing from real financial operations.

The lease is longer than the agreed 30-second total AI deadline. AI deadline enforcement, critic timeout/schema-repair handling, typed provider tools, the four policy prompt files and live Gemma validation belong to `backend/ai` and remain pending. There is no provider adapter in this change.

## Checks to run next

Run migrations, migration drift check, Django check, pytest, and Ruff after dependencies are available. Tests cover ownership, payment eligibility/periods, idempotency, critic rejection/malformed input, cancellation confirmation/expiry/staleness, handoff/stale AI, lease recovery, message deduplication, operator permissions and login CSRF. Run concurrency tests on PostgreSQL. Then connect the AI boundary and verify the primary activation scenario through the frontend; frontend build and a separately identified live model smoke test remain pending.

References: [DRF session authentication and login CSRF](https://www.django-rest-framework.org/api-guide/authentication/#sessionauthentication), [Django transaction locking](https://docs.djangoproject.com/en/dev/ref/models/querysets/#select-for-update), [SQLite transaction mode](https://docs.djangoproject.com/en/dev/ref/databases/#sqlite-notes).
