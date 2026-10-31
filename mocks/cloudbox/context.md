# CloudBox

CloudBox is a cloud file storage service sold by subscription. Every customer has exactly one
subscription on one of three plans:

| Plan | Price, UAH per 30 days | Storage |
|------|------------------------|---------|
| Free | 0                      | 5 GB    |
| Plus | 99                     | 100 GB  |
| Pro  | 199                    | 1000 GB |

A customer buys a plan with a payment. A **successful** payment has to be **applied** to the
subscription: that switches the plan and moves `period_end` forward by the paid period.
Applying normally happens automatically, but sometimes it fails, and the customer sees
"I paid, but my plan did not change". Such a payment has `status = 'successful'` and
`applied_at IS NULL`.

## Support rules

- A successful, unapplied payment may be applied with `POST /subscription/sync`. Applying it
  twice is impossible: the API refuses an already applied payment.
- Turning off auto-renewal keeps the plan and access until `period_end`. Nothing is refunded.
- A refund is possible only for a successful payment, up to the amount not yet refunded.
  A refund does not change the plan.
- Failed and pending payments cannot be applied or refunded.
- CloudBox support never changes a customer's email, payment card or password, and never
  deletes accounts.

## API

Every request is made on behalf of one customer, so paths name no customer: `/payments` are the
current customer's payments. JSON in, JSON out. An error is a 4xx status with
`{"detail": "..."}`. Another customer's object answers 404, exactly like a missing one.

| Method | Path | Body | Result |
|--------|------|------|--------|
| GET  | `/me` | | the customer's profile |
| GET  | `/subscription` | | the subscription with its plan |
| GET  | `/payments` | | payments, newest first |
| POST | `/subscription/sync` | `{"payment_id": "pay-501"}` | applies the payment; returns the subscription |
| POST | `/subscription/auto-renewal/off` | `{}` | returns the subscription |
| POST | `/subscription/auto-renewal/on` | `{}` | returns the subscription |
| POST | `/payments/{payment_id}/refund` | `{"amount": 99, "reason": "..."}` | returns the payment |

## Database schema

Dates are ISO 8601 strings in UTC. Money is in UAH.

```sql
CREATE TABLE customers (
    id    TEXT PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL
);

CREATE TABLE plans (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    price      REAL NOT NULL,
    storage_gb INTEGER NOT NULL
);

CREATE TABLE subscriptions (
    id          TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL UNIQUE REFERENCES customers (id),
    plan_id     TEXT NOT NULL REFERENCES plans (id),
    status      TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
    period_end  TEXT,
    auto_renew  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE payments (
    id          TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers (id),
    plan_id     TEXT NOT NULL REFERENCES plans (id),
    amount      REAL NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('successful', 'failed', 'pending')),
    period_days INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    applied_at  TEXT,
    refunded    REAL NOT NULL DEFAULT 0
);
```
