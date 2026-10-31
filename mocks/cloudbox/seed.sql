INSERT INTO customers (id, name, email) VALUES
    ('c-101', 'Олена Коваль', 'olena@example.com'),
    ('c-102', 'Андрій Мельник', 'andrii@example.com'),
    ('c-103', 'Ірина Бондар', 'iryna@example.com');

INSERT INTO plans (id, name, price, storage_gb) VALUES
    ('free', 'Free', 0, 5),
    ('plus', 'Plus', 99, 100),
    ('pro', 'Pro', 199, 1000);

-- c-101 paid for Plus, but the payment was never applied: still on Free.
-- c-102 is on Pro with auto-renewal. c-103 was charged twice for the same month of Plus.
INSERT INTO subscriptions (id, customer_id, plan_id, status, period_end, auto_renew) VALUES
    ('sub-1', 'c-101', 'free', 'active', NULL, 0),
    ('sub-2', 'c-102', 'pro', 'active', '2026-11-20T00:00:00+00:00', 1),
    ('sub-3', 'c-103', 'plus', 'active', '2026-11-25T00:00:00+00:00', 1);

INSERT INTO payments (id, customer_id, plan_id, amount, status, period_days, created_at, applied_at) VALUES
    ('pay-501', 'c-101', 'plus', 99, 'successful', 30, '2026-10-30T09:12:00+00:00', NULL),
    ('pay-500', 'c-101', 'plus', 99, 'failed', 30, '2026-10-30T09:05:00+00:00', NULL),
    ('pay-502', 'c-102', 'pro', 199, 'successful', 30, '2026-10-21T08:00:00+00:00', '2026-10-21T08:00:05+00:00'),
    ('pay-503', 'c-103', 'plus', 99, 'successful', 30, '2026-10-26T11:00:00+00:00', '2026-10-26T11:00:04+00:00'),
    ('pay-504', 'c-103', 'plus', 99, 'successful', 30, '2026-10-26T11:00:40+00:00', '2026-10-26T11:00:44+00:00');
