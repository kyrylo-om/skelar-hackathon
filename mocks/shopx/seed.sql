INSERT INTO customers (id, name, email, phone) VALUES
    ('s-201', 'Олена Коваль', 'olena@example.com', '+380501112233'),
    ('s-202', 'Максим Ткаченко', 'maksym@example.com', '+380674445566');

INSERT INTO orders (number, customer_id, status, total, address, tracking, created_at, delivered_at) VALUES
    ('1042', 's-201', 'processing', 1299, 'Київ, вул. Хрещатик, 1, кв. 5', NULL, '2026-10-30T10:00:00+00:00', NULL),
    ('1043', 's-201', 'delivered', 3498, 'Київ, вул. Хрещатик, 1, кв. 5', '59000123456789', '2026-10-20T12:30:00+00:00', '2026-10-23T15:00:00+00:00'),
    ('1044', 's-201', 'shipped', 350, 'Київ, вул. Хрещатик, 1, кв. 5', '59000987654321', '2026-10-28T08:15:00+00:00', NULL),
    ('2001', 's-202', 'processing', 14999, 'Львів, пл. Ринок, 10', NULL, '2026-10-29T17:45:00+00:00', NULL);

INSERT INTO order_items (order_number, title, quantity, price) VALUES
    ('1042', 'Бездротова мишка Logitech M650', 1, 1299),
    ('1043', 'Кавоварка Delonghi EC685', 1, 2999),
    ('1043', 'Набір чашок для еспресо', 1, 499),
    ('1044', 'Книга «Кобзар»', 1, 350),
    ('2001', 'Смартфон Samsung A55', 1, 14999);
