# ShopX

ShopX is an online electronics and home goods store in Ukraine. Customers place orders that move
through these statuses:

`processing` → `shipped` → `delivered`, or `processing` → `cancelled`.

An order is paid when it is placed. Delivery is by Nova Poshta; a shipped order has a tracking
number.

## Support rules

- An order can be cancelled only while it is `processing`. The customer gets the full amount back
  automatically; no separate refund is needed.
- The delivery address can be changed only while the order is `processing`.
- A refund is possible only for a `delivered` order: for a damaged or missing item, or a return
  within 14 days of delivery. Refunds of one order never add up to more than its total.
- A shipped order can be neither cancelled nor redirected: the customer waits for delivery and
  then asks for a return.
- ShopX support never changes a customer's email, phone or payment card, and never deletes
  accounts.

## API

Every request is made on behalf of one customer, so paths name no customer: `/orders` are the
current customer's orders. JSON in, JSON out. An error is a 4xx status with
`{"detail": "..."}`. Another customer's order answers 404, exactly like a missing one.

| Method | Path | Body | Result |
|--------|------|------|--------|
| GET   | `/me` | | the customer's profile |
| GET   | `/orders` | | orders, newest first |
| GET   | `/orders/{number}` | | the order with its items and refunds |
| POST  | `/orders/{number}/cancel` | `{}` | the order |
| PATCH | `/orders/{number}/address` | `{"address": "Київ, вул. Хрещатик, 1"}` | the order |
| POST  | `/orders/{number}/refund` | `{"amount": 300, "reason": "..."}` | the order |

## Database schema

Dates are ISO 8601 strings in UTC. Money is in UAH.

```sql
CREATE TABLE customers (
    id    TEXT PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL
);

CREATE TABLE orders (
    number       TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers (id),
    status       TEXT NOT NULL CHECK (status IN ('processing', 'shipped', 'delivered', 'cancelled')),
    total        REAL NOT NULL,
    address      TEXT NOT NULL,
    tracking     TEXT,
    created_at   TEXT NOT NULL,
    delivered_at TEXT
);

CREATE TABLE order_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL REFERENCES orders (number),
    title        TEXT NOT NULL,
    quantity     INTEGER NOT NULL,
    price        REAL NOT NULL
);

CREATE TABLE refunds (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL REFERENCES orders (number),
    amount       REAL NOT NULL,
    reason       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
```
