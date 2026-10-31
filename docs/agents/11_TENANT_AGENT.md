# Tenant Agent (Інтеграція зовнішніх продуктів)

Агент, що взаємодіє з будь-яким підключеним продуктом через його документацію (`context.md`) та API, керований детермінованими правилами безпеки (`manifest.yaml`).

## 1. Архітектура

```
повідомлення клієнта -> Guard -> (чат уже в людини?) -> session_for(user) ?
   так: цикл агента (читає API) -> write? -> Session.prepare_write -> gate_plan(Critic, Policy)
        execute: Session.execute_write (propose -> execute через execution server) -> Responder
        review : черга людини (ReviewItem з action=<tenant>.<endpoint>), після схвалення execute_approved
        block  : відмова
   ні:  наявний шлях (Triage -> Actor -> Gate -> DevDomainGateway), без змін
```

## 2. Формат `manifest.yaml`

Правила безпеки для дій продукту є декларативними даними:

```yaml
tenant: cloudbox
name: CloudBox
policies:
  rate_limit_per_hour: 5
  idempotency_window_sec: 120
  review_vip: true
rules:
  - match: "POST /subscription/sync"
    risk: medium
    summary: "Активувати підписку за платежем {payment_id}"
    requires:
      - read: "GET /payments"
        where:
          id: "{payment_id}"
        field: status
        in: [successful]
      - read: "GET /payments"
        where:
          id: "{payment_id}"
        field: applied_at
        empty: true
  - match: "POST /payments/{payment_id}/refund"
    risk: high
    summary: "Повернути {amount} грн за платіж {payment_id}"
    limits:
      amount_param: amount
      auto_max: 50
      hard_max: 1000
    requires:
      - read: "GET /payments"
        where:
          id: "{payment_id}"
        field: status
        in: [successful]
```

## 3. Як підключити новий продукт (3 кроки)

1. **Документація продукту (`context.md`)**:
   Опишіть бізнес-контекст продукту, таблицю доступних API-ендпоінтів та схему бази даних (наприклад, як у `mocks/cloudbox/context.md` або `mocks/shopx/context.md`).
2. **Маніфест правил (`manifest.yaml`)**:
   Створіть папку `backend/tenants/<tenant_name>/manifest.yaml` з правилами ризику, передумовами (`requires`) та лімітами. Дії без правил за замовчуванням мають ризик `high` (вимагають схвалення людини).
3. **Реєстрація та користувач**:
   Додайте продукт у `execution/products.toml` та створіть запис `TenantCustomer(user, tenant, external_id)` для мапінгу клієнта.

## 4. Гарантії безпеки

| Загроза | Механізм захисту |
|---|---|
| Витік токена | Токен ніколи не потрапляє в промпт, контекст LLM, trace чи журнал `ApiCall` |
| Несанкціонований запис | Цикл агента може лише читати (`GET`). Будь-який запис зупиняє цикл і проходить Critic та Policy |
| Підміна чужих ID | Дозволені лише ті ID, які були повернуті з попередніх авторизованих читань самого клієнта (`seen / verified`) |
| Фальсифікація умов | Умови `requires` перевіряються запитом до API продукту, а не словами клієнта |
| Збій сервісу | Fail-closed: будь-яка помилка передає діалог людині |

## 5. Межі поточної реалізації

* **MCP execution server**: у тестовому середовищі використовується `FakeExecutionClient` над реальними інстансами Starlette моків.
* **Rollback / Undo**: запити на відкат для зовнішніх продуктів реєструються як окремі компенсуючі операції.
