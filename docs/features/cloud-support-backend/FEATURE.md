# Cloud Support backend

Status: **partial**. Inspected implementation: commit `a42b8b61100e3b82affa67f18a28d117a1267521`; documentation added in the working tree. Evidence is source inspection, not a successful application run. The bundle covers all current project backend modules, including the original health endpoint.

Customers need help with synthetic cloud-storage subscriptions; staff need to continue the same conversation. The backend provides session authentication, subscription reads, persisted conversations, a provider-unavailable handoff and operator APIs. Internal domain services implement paid-plan synchronization and cancellation proposals with review and confirmation boundaries. Real payment processing, bank refunds and storage provisioning are out of scope.

## Capability and acceptance status

| Capability / acceptance criterion | Implementation | Runtime verification |
| --- | --- | --- |
| Public health endpoint bootstraps a CSRF cookie | implemented | Not verified; tests exist |
| Login/logout/current user with session and CSRF | implemented | Not verified; login/CSRF test exists |
| Customer sees only their subscription/conversations/actions | implemented in handlers/services | Not verified; ownership tests exist |
| Apply exact purchased entitlement once | partial: internal services only, no chat caller | Not verified; replay and PostgreSQL concurrency tests exist |
| Disable renewal only after endpoint confirmation; preserve paid access | partial: confirmation API exists, no production proposal caller | Not verified; confirmation/staleness tests exist |
| Store customer messages once; recover expired turn lease | implemented | Not verified; duplicate/lease tests exist |
| Transfer to same-chat operator queue, claim, reply and resolve | implemented backend paths; no product UI | Not verified; operator tests exist |
| Live actor/critic orchestration and bounded provider failure handling | planned; no adapter or provider calls | Not verified |
| Seed synthetic scenarios without resetting progressed state | implemented command | Not verified; idempotency test exists |

`implemented` describes code presence and traced control flow, not a security guarantee or a passing acceptance check. Declared migrations have not been verified against a running database in this session. The previous implementation session recorded failed dependency installation due to PyPI DNS resolution; no runtime checks were repeated for this documentation-only change.

## Navigation

- [Business context and rules](business-context.md)
- [End-to-end flows](end-to-end-flow.md)
- [Verified code entry index](entry-points.json)
- [App and module responsibilities](per-app-responsibility.md)
- [Frontend structure and missing product screens](frontend-structure.md)
- [Backend routes, services and verification map](backend-structure.md)
- [Data model, constraints and lifecycle](data-model.md)
- [Integration contracts](integration-points.md)
- [Known limitations and risks](known-gotchas.md)

## Local verification entry

See [backend setup and handoff](../../BACKEND.md) and [root setup instructions](../../../README.md). With dependencies and environment configured, run from `backend/`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
ruff check .
ruff format --check .
```

These are follow-up commands, not results of this documentation task. PostgreSQL is required for the two row-lock concurrency tests. The current default is the template's SQLite, with optional `DATABASE_URL` selection. Database initialization and `seed_demo` are documented separately; this documentation task did not apply migrations, seed data or install dependencies.

## Documentation validation performed

The documentation-only validation checked all ten required files, the exact JSON schema, 32 unique entry records, source symbols, all 15 configured API routes and declared methods, 46 local Markdown links, overview navigation and rule references. A placeholder/credential-pattern scan found no matches; this is not a comprehensive secret audit. Application code was not changed, migrations were not applied, and backend/frontend runtime tests were not run. `git diff --check` passed for tracked documentation changes; newly created bundle files were separately checked for trailing whitespace.
