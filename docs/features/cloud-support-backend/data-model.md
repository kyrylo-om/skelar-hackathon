# Data model

Status: model and migration declarations inspected; live schema, applied migrations and persisted data are **Not verified**. Fields below are exact declarations from the source, including null/blank/default/relationship arguments; unspecified nullability uses the Django field default. All six project entity IDs are generated UUID primary keys.

## Entities and fields

### Plan

Evidence: [subscriptions/models.py](../../../backend/apps/subscriptions/models.py), `Plan`. Default Django table: `subscriptions_plan` (no custom db_table); actual database creation is not verified.

| Field | Source declaration |
| --- | --- |
| `id` | `models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)` |
| `name` | `models.CharField(max_length=32, unique=True)` |
| `price` | `models.DecimalField(max_digits=10, decimal_places=2)` |
| `currency` | `models.CharField(max_length=3, default='UAH')` |
| `storage_limit_gb` | `models.PositiveIntegerField()` |

### Subscription

Evidence: [subscriptions/models.py](../../../backend/apps/subscriptions/models.py), `Subscription`. Default Django table: `subscriptions_subscription` (no custom db_table); actual database creation is not verified.

| Field | Source declaration |
| --- | --- |
| `id` | `models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)` |
| `user` | `models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)` |
| `plan` | `models.ForeignKey(Plan, on_delete=models.PROTECT)` |
| `status` | `models.CharField(max_length=16, default='active', choices=[('active', 'active'), ('inactive', 'inactive')])` |
| `period_end` | `models.DateTimeField(null=True, blank=True)` |
| `auto_renew` | `models.BooleanField(default=False)` |
| `version` | `models.PositiveIntegerField(default=0)` |

### Payment

Evidence: [subscriptions/models.py](../../../backend/apps/subscriptions/models.py), `Payment`. Default Django table: `subscriptions_payment` (no custom db_table); actual database creation is not verified.

| Field | Source declaration |
| --- | --- |
| `id` | `models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)` |
| `user` | `models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)` |
| `plan` | `models.ForeignKey(Plan, on_delete=models.PROTECT)` |
| `amount` | `models.DecimalField(max_digits=10, decimal_places=2)` |
| `currency` | `models.CharField(max_length=3, default='UAH')` |
| `status` | `models.CharField(max_length=16, choices=[('successful', 'successful'), ('failed', 'failed'), ('pending', 'pending')])` |
| `period_start` | `models.DateTimeField()` |
| `period_end` | `models.DateTimeField()` |
| `applied_at` | `models.DateTimeField(null=True, blank=True)` |
| `created_at` | `models.DateTimeField(auto_now_add=True)` |
| `demo_reference` | `models.CharField(max_length=64, unique=True, null=True, blank=True)` |

### Conversation

Evidence: [support/models.py](../../../backend/apps/support/models.py), `Conversation`. Default Django table: `support_conversation` (no custom db_table); actual database creation is not verified.

| Field | Source declaration |
| --- | --- |
| `id` | `models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)` |
| `user` | `models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)` |
| `status` | `models.CharField(max_length=24, default='ai', choices=[(s, s) for s in ('ai', 'waiting_operator', 'operator', 'resolved')])` |
| `assigned_operator` | `models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='assigned_conversations')` |
| `summary` | `models.TextField(blank=True)` |
| `version` | `models.PositiveIntegerField(default=0)` |
| `in_flight_token` | `models.UUIDField(null=True, blank=True)` |
| `in_flight_at` | `models.DateTimeField(null=True, blank=True)` |
| `created_at` | `models.DateTimeField(auto_now_add=True)` |

### Message

Evidence: [support/models.py](../../../backend/apps/support/models.py), `Message`. Default Django table: `support_message` (no custom db_table); actual database creation is not verified.

| Field | Source declaration |
| --- | --- |
| `id` | `models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)` |
| `conversation` | `models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')` |
| `sender` | `models.CharField(max_length=16, choices=[(s, s) for s in ('customer', 'assistant', 'operator', 'system')])` |
| `sender_user` | `models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)` |
| `text` | `models.TextField()` |
| `client_message_id` | `models.CharField(max_length=128, null=True, blank=True)` |
| `response` | `models.JSONField(null=True, blank=True)` |
| `created_at` | `models.DateTimeField(auto_now_add=True)` |

### Action

Evidence: [support/models.py](../../../backend/apps/support/models.py), `Action`. Default Django table: `support_action` (no custom db_table); actual database creation is not verified.

| Field | Source declaration |
| --- | --- |
| `id` | `models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)` |
| `conversation` | `models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='actions')` |
| `requesting_user` | `models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)` |
| `subscription` | `models.ForeignKey('subscriptions.Subscription', on_delete=models.PROTECT)` |
| `payment` | `models.ForeignKey('subscriptions.Payment', on_delete=models.PROTECT, null=True, blank=True)` |
| `kind` | `models.CharField(max_length=32, choices=[('sync_subscription', 'sync_subscription'), ('cancel_auto_renewal', 'cancel_auto_renewal')])` |
| `parameters` | `models.JSONField(default=dict)` |
| `status` | `models.CharField(max_length=32, default='proposed', choices=[(s, s) for s in ('proposed', 'awaiting_confirmation', 'executing', 'succeeded', 'failed', 'rejected', 'expired')])` |
| `expires_at` | `models.DateTimeField()` |
| `expected_version` | `models.PositiveIntegerField()` |
| `conversation_version` | `models.PositiveIntegerField()` |
| `critic_decision` | `models.CharField(max_length=16, blank=True)` |
| `critic_reason` | `models.CharField(max_length=1000, blank=True)` |
| `evidence` | `models.JSONField(default=dict)` |
| `idempotency_key` | `models.UUIDField(default=uuid.uuid4, unique=True, editable=False)` |
| `result` | `models.JSONField(default=dict)` |
| `created_at` | `models.DateTimeField(auto_now_add=True)` |

## Constraints, ownership and source of truth

- `Subscription.user` is OneToOne: at most one per user; application code does not automatically create one at login. Plan FKs use PROTECT.
- `Plan.name` is unique. Money uses DecimalField(max_digits=10, decimal_places=2); payment amount has the declared nonnegative check. There is no plan-price nonnegative check or enforced uppercase/currency enum.
- `Payment` declares payment_positive_period (`period_end > period_start`) and payment_nonnegative_amount. demo_reference is nullable unique for seed identity. No DB unique constraint binds a payment to only one successful Action; the service uses subscription/payment locks and applied_at checks.
- `Message` declares unique_client_message on conversation/sender/client_message_id; nullable client IDs permit assistant/system messages without a submitted ID. Ordering is created_at then id. Deduplication is per sender kind, not per staff-user ID.
- `Action.idempotency_key` is a unique server-generated UUID. It is not a submitted HTTP idempotency header. Action parameters/evidence/result are JSON objects set by services; the model itself has no immutable-field override or DB transition trigger.
- User ownership comes from authenticated service arguments and scoped ORM queries. Foreign-key user equality across Conversation/Action/Subscription/Payment is not a DB check; raw ORM calls are a trusted boundary.
- User, session and staff state live in built-in Django auth/session tables configured in settings, not custom accounts models. Customer API user IDs are strings derived from Django PKs; project UUIDs do not imply a custom UUID User model.
- Conversation user deletion cascades; assigned_operator uses PROTECT. Message sender_user, Action requesting_user/subscription/payment use PROTECT. No user deletion or retention workflow is implemented.

## Lifecycle and read/write effects

Conversation choices are ai, waiting_operator, operator, resolved; actual transitions are in [end-to-end-flow.md](end-to-end-flow.md). version increases for new/recovered customer turns, handoff, claim, new operator replies and first resolve. finish_turn clears the token without incrementing version. A completed duplicate customer/operator message does not create another message.

Subscription choices are active/inactive; synchronization writes active, exact payment plan/period_end and version+1, leaving auto_renew unchanged. Cancellation writes only auto_renew=False and version+1. There is no period-start field on Subscription, quota accumulator, recurring renewal job or cancellation deletion.

Payment choices are successful/failed/pending. Domain synchronization only sets applied_at; payment status and recorded purchase values are not rewritten. Payment creation in current application code occurs in seed_demo (and tests), not through HTTP payment ingestion.

Action choices are proposed, awaiting_confirmation, executing, succeeded, failed, rejected, expired. Actual code creates proposed, changes allowed cancellations to awaiting_confirmation, rejects non-allow/missing-info reviews and pending handoff candidates, and sets successful execution to succeeded. A review-allowed sync remains proposed until execution. executing/failed/expired are declared but not assigned by the current services. Expiry is enforced by time checks, not a background transition.

Evidence stores subscription_id, subscription_version and optional payment_id. parameters stores payment_id for sync and an empty object for cancellation; expected_version and conversation_version are separate columns. critic_reason is concise text, not hidden reasoning. Successful result contains a serialized subscription snapshot and simulated_billing=true. ChatResult is cached on customer Message.response, distinct from Action.result.

## Migrations and demo data

[subscriptions/0001_initial.py](../../../backend/apps/subscriptions/migrations/0001_initial.py) declares Plan, Subscription, Payment and payment checks, depending on the swappable auth user. [support/0001_initial.py](../../../backend/apps/support/migrations/0001_initial.py) declares Conversation, Message, Action and message uniqueness; it depends on subscriptions and auth. Migrations are not evidence that these tables already exist in a running DB.

[seed_demo.py](../../../backend/apps/support/management/commands/seed_demo.py), Command.handle, seeds three plans and customer users paid_plus, active_pro, refund_review plus staff operator. paid_plus starts on Free with unapplied Plus payment; active_pro/Pro and refund_review/Plus have applied payments and renewal enabled. Dates are seed-relative; get_or_create preserves older dates and progressed state. A local password is supplied through DEMO_PASSWORD, not embedded in this documentation.

## Retention and sensitive data

Transcript text, summary and result snapshots persist in the database. Configured retention, redaction, encryption-at-rest and deletion policy: **unknown / Not verified**. Summary copies the last three customer request texts and attempted action results; it is not a substitute for the full transcript. No credentials/raw session tokens are model fields in these entities. The planned AI adapter must avoid sending lease tokens or unrelated customer data into prompts.
