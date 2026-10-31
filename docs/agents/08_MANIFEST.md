# 08. Маніфест tenant-а

Статус: чернетка. **[узгодити]** позначає пункти без підтвердження команди. Маніфесту в коді ще немає: реєстр
дій зараз локальний словник у `backend/apps/security/policy.py`, пороги в `settings.py`.

## Призначення
Закриває проблему «як підключити будь-який продукт з підпискою без переписування коду»: маніфест описує
сутності, дії, передумови, ліміти й політики конкретного клієнта (tenant-а), а механіка конвеєра в коді лишається
однаковою. Це робить безпеку доменно-незалежною.

## Принципи
1. **Механіка в коді, правила в маніфесті.** Код знає абстрактні передумови й порядок правил; маніфест задає
   числа, назви полів і ендпоінти ([05_POLICY.md](05_POLICY.md)).
2. **Маніфест не може послабити інваріанти** ([00_OVERVIEW.md](00_OVERVIEW.md)): не можна вимкнути Policy,
   перевірку власника, повторну перевірку після схвалення чи аудит. Завантаження маніфесту це відхиляє.
3. **Секрети лише за посиланням** (`secret_ref: env:NAME`); у файлі їх немає, LLM їх не бачить.
4. **Fail closed.** Невалідний або неповний маніфест: tenant не активується, жодна дія не виконується.
5. **Версіонування.** `manifest_version` і зміна ліміту проходять перевірку (lint) до застосування.

## 1. YAML-схема з коментарями

```yaml
manifest_version: 1                       # версія схеми маніфесту

tenant:
  id: acme-cloud                          # унікальний id tenant-а (береться із сесії запиту, не з тексту)
  name: CloudBox                          # бренд у відповідях
  locale: [uk, en]                        # мови підтримки
  default_language: uk
  timezone: Europe/Kyiv
  currency: UAH                           # валюта сум у правилах

access:                                   # як сервіс звертається до API продукту
  base_url: https://api.example.com/v1
  auth:
    type: bearer                          # bearer | api_key_header | basic
    secret_ref: env:ACME_SERVICE_TOKEN    # посилання на секрет, не сам секрет
  timeout_ms: 3000
  retries: 1
  identity:
    user_id_source: session               # customer_id береться лише із сесії
    user_id_claim: sub                    # яке поле сесії містить id клієнта в продукті

entities:                                 # мапінг сутностей продукту
  user:
    endpoint: GET /users/{customer_id}
    id_field: id
    status_field: status
    active_statuses: [active]             # передумова user_exists
    vip_field: tier                       # необов'язково: для правила VIP
    vip_values: [pro]
  resources:                              # ресурси, з якими працюють дії
    <resource_name>:
      endpoint: GET /users/{customer_id}/<path>     # як дістати ресурс клієнта
      id_field: id
      owner_field: user_id                          # поле власника (для user_owns_resource)
      status_field: status
      statuses: [..]                                # допустимі статуси
      amount_field: amount                          # необов'язково: сума ресурсу
      version_field: version                        # необов'язково: захист від застарілих даних
      confirmed_statuses: [..]                      # для платежів: що вважається успішним
      applied_field: applied                        # для платежів: чи вже використано

actions:                                  # єдині дії, які взагалі існують для tenant-а
  <action_name>:
    description: "..."                    # потрапляє в промпт Actor
    risk: low | medium | high
    params:                               # параметри дії
      <param>:
        type: string | integer | number | boolean
        source: facts.<resource>[].<field>   # звідки брати значення (з контексту, не з тексту клієнта)
        resource: <resource_name>            # до якого ресурсу належить значення
        min: 0                               # необов'язково
    amount_param: <param>                 # якщо дія має суму (вмикає правила 7a-7c)
    preconditions:                        # абстрактні передумови (список з 05_POLICY.md)
      - user_exists
      - user_owns_resource: {resource: <name>, param: <param>}
      - payment_confirmed: {param: <param>}
      - resource_status_in: {resource: <name>, statuses: [..]}
      - amount_within_limit
      - rate_limit_ok
      - not_duplicate
    limits:
      auto: 50                            # до цієї суми дія може йти без людини
      hard: 1000                          # вище цього deny, людина не обходить
    confirm: none | customer | human      # хто підтверджує
    editable_by_reviewer: [amount]        # що оператор може зменшити при схваленні [узгодити]
    undo:
      action: <action_name> | null        # компенсувальна дія
      window_sec: 600
    executor:                             # як модуль дій викликає продукт
      method: POST
      endpoint: /...
      body: {param: "{param}"}

policies:
  rate_limit: {risky_actions_per_hour: 5}
  idempotency_window_sec: 120
  daily_cumulative:                       # захист від дроблення суми
    refund: {actions: [issue_refund], limit: 2000}
  review_high_risk: true
  review_vip: true
  always_review: [escalate_to_human]      # дії, які завжди йдуть до людини

escalation:
  max_clarifications: 2                   # скільки уточнень поспіль до передачі людині
  max_rejections: 2                       # скільки відхилень Critic до передачі людині
  confidence_threshold: 0.6
  complaints_before_human: 2
  legal_terms: [суд, прокуратура, lawsuit, chargeback]
  always_human_intents: [legal_threat, account_deletion]
  review_sla_minutes: 60                  # [узгодити]

intents:                                  # що розпізнаємо і які дії дозволені
  - id: <intent_id>
    allowed_actions: [<action_name>, ...]
    retention: pause | downgrade | none   # що запропонувати перед скасуванням

guard:
  extra_blocked_topics: []                # додаткові заборонені теми tenant-а
  extra_doubtful_terms: []                # слова, що відправляють текст на LLM-перевірку

responses:                                # шаблони відповідей (мова -> текст)
  review: {uk: "Передав ваш запит спеціалісту, відповімо в цьому чаті."}
  block:  {uk: "Не можу виконати цей запит. Опишіть, будь ласка, вашу ситуацію."}
  failed: {uk: "Не вдалося завершити дію. Я вже передав запит спеціалісту."}

audit:
  retention_days: 365                     # [узгодити]
  redact: [card_number, email, phone]
```

### Правила валідації маніфесту (lint при завантаженні)
- Кожна дія в `intents[].allowed_actions` та `policies` існує в `actions`.
- Для дій із `amount_param` задано `limits.hard`, і `limits.auto ≤ limits.hard`.
- Дія з `risk: high` має `confirm: human`.
- Дії без `user_owns_resource` для параметрів-ресурсів відхиляються (не можна оголосити дію без перевірки власника).
- Заборонено вимикати інваріанти (немає ключів `skip_policy`, `skip_audit`, `disable_ownership_check`).
- `secret_ref` вказує на існуючу змінну; секрети у відкритому вигляді відхиляються.
- Усі `source` вказують на ресурс із `entities.resources`.

## 2. Приклад A: SaaS-підписка (хмарне сховище)

```yaml
manifest_version: 1
tenant: {id: cloudbox, name: CloudBox, locale: [uk, en], default_language: uk, timezone: Europe/Kyiv, currency: UAH}
access:
  base_url: https://api.cloudbox.example/v1
  auth: {type: bearer, secret_ref: env:CLOUDBOX_SERVICE_TOKEN}
  timeout_ms: 3000
  retries: 1
  identity: {user_id_source: session, user_id_claim: sub}

entities:
  user:
    endpoint: GET /users/{customer_id}
    id_field: id
    status_field: status
    active_statuses: [active]
    vip_field: plan
    vip_values: [pro]
  resources:
    subscription:
      endpoint: GET /users/{customer_id}/subscription
      id_field: id
      owner_field: user_id
      status_field: status
      statuses: [active, canceled, past_due]
      version_field: version
    payment:
      endpoint: GET /users/{customer_id}/payments
      id_field: id
      owner_field: user_id
      status_field: status
      confirmed_statuses: [succeeded]
      applied_field: applied
      amount_field: amount

actions:
  sync_subscription:
    description: "Apply a paid but not yet applied payment to the subscription"
    risk: low
    params:
      payment_id: {type: string, source: "facts.payments[].id", resource: payment}
    preconditions:
      - user_exists
      - user_owns_resource: {resource: payment, param: payment_id}
      - payment_confirmed: {param: payment_id}
      - not_duplicate
    confirm: none
    undo: {action: null}
    executor: {method: POST, endpoint: "/subscriptions/{subscription_id}/sync", body: {payment_id: "{payment_id}"}}

  cancel_auto_renewal:
    description: "Turn off automatic renewal; access stays until the end of the paid period"
    risk: medium
    params:
      subscription_id: {type: string, source: "facts.subscription.id", resource: subscription}
    preconditions:
      - user_exists
      - user_owns_resource: {resource: subscription, param: subscription_id}
      - resource_status_in: {resource: subscription, statuses: [active]}
      - not_duplicate
    confirm: customer
    undo: {action: resume_auto_renewal, window_sec: 2592000}
    executor: {method: POST, endpoint: "/subscriptions/{subscription_id}/auto-renewal/off", body: {}}

  issue_refund:
    description: "Refund a succeeded payment; always decided by a human"
    risk: medium
    params:
      payment_id: {type: string, source: "facts.payments[].id", resource: payment}
      amount: {type: number, min: 0}
    amount_param: amount
    preconditions:
      - user_exists
      - user_owns_resource: {resource: payment, param: payment_id}
      - payment_confirmed: {param: payment_id}
      - amount_within_limit
      - rate_limit_ok
      - not_duplicate
    limits: {auto: 0, hard: 1000}          # auto: 0 означає, що повернення завжди через людину
    confirm: human
    editable_by_reviewer: [amount]
    undo: {action: null}
    executor: {method: POST, endpoint: "/payments/{payment_id}/refund", body: {amount: "{amount}"}}

  escalate_to_human:
    description: "Hand the conversation to a support specialist"
    risk: low
    params: {reason: {type: string}}
    preconditions: [user_exists]
    confirm: human
    undo: {action: null}

policies:
  rate_limit: {risky_actions_per_hour: 5}
  idempotency_window_sec: 120
  daily_cumulative: {refund: {actions: [issue_refund], limit: 2000}}
  review_high_risk: true
  review_vip: true
  always_review: [escalate_to_human, issue_refund]

escalation:
  max_clarifications: 2
  max_rejections: 2
  confidence_threshold: 0.6
  complaints_before_human: 2
  legal_terms: [суд, lawsuit, chargeback]
  always_human_intents: [legal_threat, account_deletion, payment_method_change]

intents:
  - {id: activation_issue,  allowed_actions: [sync_subscription]}
  - {id: subscription_status, allowed_actions: []}
  - {id: cancel_renewal,    allowed_actions: [cancel_auto_renewal], retention: downgrade}
  - {id: refund,            allowed_actions: [issue_refund]}
  - {id: human_request,     allowed_actions: [escalate_to_human]}
  - {id: info_question,     allowed_actions: []}
```

## 3. Приклад B: e-commerce

```yaml
manifest_version: 1
tenant: {id: shopx, name: ShopX, locale: [uk], default_language: uk, timezone: Europe/Kyiv, currency: UAH}
access:
  base_url: https://shop.example/api
  auth: {type: api_key_header, secret_ref: env:SHOPX_API_KEY}
  timeout_ms: 3000
  retries: 1
  identity: {user_id_source: session, user_id_claim: customer_id}

entities:
  user:
    endpoint: GET /customers/{customer_id}
    id_field: id
    status_field: state
    active_statuses: [active]
    vip_field: vip
    vip_values: [true]
  resources:
    order:
      endpoint: GET /customers/{customer_id}/orders
      id_field: number
      owner_field: customer_id
      status_field: status
      statuses: [processing, shipped, delivered, canceled]
      amount_field: total

actions:
  get_order_status:
    description: "Read the status and tracking of the customer's order"
    risk: low
    params:
      order: {type: string, source: "facts.orders[].number", resource: order}
    preconditions:
      - user_exists
      - user_owns_resource: {resource: order, param: order}
    confirm: none
    undo: {action: null}

  change_address:
    description: "Change the delivery address of an order that is still being processed"
    risk: medium
    params:
      order:   {type: string, source: "facts.orders[].number", resource: order}
      address: {type: string}
    preconditions:
      - user_exists
      - user_owns_resource: {resource: order, param: order}
      - resource_status_in: {resource: order, statuses: [processing]}
      - rate_limit_ok
      - not_duplicate
    confirm: customer
    undo: {action: restore_address, window_sec: 600}
    executor: {method: PATCH, endpoint: "/orders/{order}/address", body: {address: "{address}"}}

  cancel_order:
    description: "Cancel an order that is still being processed"
    risk: medium
    params:
      order: {type: string, source: "facts.orders[].number", resource: order}
    preconditions:
      - user_exists
      - user_owns_resource: {resource: order, param: order}
      - resource_status_in: {resource: order, statuses: [processing]}
      - rate_limit_ok
      - not_duplicate
    confirm: customer
    undo: {action: restore_order, window_sec: 600}
    executor: {method: POST, endpoint: "/orders/{order}/cancel", body: {}}

  issue_refund:
    description: "Refund part or all of a delivered order"
    risk: medium
    params:
      order:  {type: string, source: "facts.orders[].number", resource: order}
      amount: {type: number, min: 0}
    amount_param: amount
    preconditions:
      - user_exists
      - user_owns_resource: {resource: order, param: order}
      - resource_status_in: {resource: order, statuses: [delivered]}
      - amount_within_limit
      - rate_limit_ok
      - not_duplicate
    limits: {auto: 50, hard: 1000}
    confirm: customer
    editable_by_reviewer: [amount]
    undo: {action: null}
    executor: {method: POST, endpoint: "/orders/{order}/refund", body: {amount: "{amount}"}}

  escalate_to_human:
    description: "Hand the conversation to a support specialist"
    risk: low
    params: {reason: {type: string}}
    preconditions: [user_exists]
    confirm: human
    undo: {action: null}

policies:
  rate_limit: {risky_actions_per_hour: 5}
  idempotency_window_sec: 120
  daily_cumulative: {refund: {actions: [issue_refund], limit: 2000}}
  review_high_risk: true
  review_vip: true
  always_review: [escalate_to_human]

escalation:
  max_clarifications: 2
  max_rejections: 2
  confidence_threshold: 0.6
  complaints_before_human: 2
  legal_terms: [суд, прокуратура]
  always_human_intents: [legal_threat, payment_method_change]

intents:
  - {id: order_status,   allowed_actions: [get_order_status]}
  - {id: change_address, allowed_actions: [change_address]}
  - {id: cancel_order,   allowed_actions: [cancel_order]}
  - {id: refund,         allowed_actions: [issue_refund]}
  - {id: human_request,  allowed_actions: [escalate_to_human]}
```

### Доказ, що код не змінюється між A і B

| Що | У прикладі A (SaaS) | У прикладі B (e-commerce) | Код |
|---|---|---|---|
| Власник | `payment.user_id` / `subscription.user_id` | `order.customer_id` | один обробник `user_owns_resource` читає `owner_field` |
| Статус | `subscription.status ∈ {active}` | `order.status ∈ {processing}` | один обробник `resource_status_in` читає `status_field` |
| Платіж підтверджено | `payment.status ∈ confirmed_statuses`, `applied=false` | не використовується | один обробник `payment_confirmed`; підключається лише там, де вказаний |
| Сума й ліміти | `amount`, `auto: 0`, `hard: 1000` | `total`, `auto: 50`, `hard: 1000` | один обробник `amount_within_limit` читає `amount_field` і `limits` |
| Rate limit, повтор, добова сума | числа з `policies` | числа з `policies` | один журнал дій і однакова математика |
| Хто підтверджує | `confirm: none/customer/human` | те саме поле | одна машина станів |
| Виконання | `executor` з шаблоном запиту | `executor` з шаблоном запиту | один HTTP-виконавець підставляє `params` |

Додати інший продукт це змінити лише YAML. Нових гілок коду для «підписки» чи «замовлення» немає.

## 4. Як підключити новий продукт за 3 кроки

1. **Опишіть сутності (`entities`).** Для кожного ресурсу (підписка, платіж, замовлення…) вкажіть ендпоінт, поле
   id, поле власника, поле статусу, поле суми та перелік статусів. Додайте `access` із посиланням на секрет.
2. **Опишіть дії (`actions`).** Для кожної дії, яку AI може виконувати: ризик, параметри з джерелом у контексті,
   передумови зі стандартного списку, ліміти, хто підтверджує, `undo` та виклик виконавця. Прив'яжіть дії до
   інтентів (`intents[].allowed_actions`).
3. **Задайте політики й пороги (`policies`, `escalation`) і перевірте.** Вкажіть rate limit, ідемпотентність,
   добові суми, пороги ескалації, шаблони відповідей. Запустіть lint маніфесту й набір автотестів
   з [09_ATTACKS.md](09_ATTACKS.md): усі атаки мають блокуватись, нормальні звернення проходити.

Команди lint і прогону каталогу атак для tenant-а ще не існують **[узгодити]**.

## Що береться з маніфесту, а що захардкожено

| Параметр | Джерело |
|---|---|
| Ендпоінти, поля, статуси, секрети за посиланням | **маніфест** |
| Дії, параметри, ризики, ліміти, undo, виконавець | **маніфест** |
| Політики, пороги ескалації, шаблони відповідей, терміни аудиту | **маніфест** |
| Список абстрактних передумов, порядок правил Policy, інваріанти, fail closed, схеми JSON | **код** |
| Валідація маніфесту при завантаженні | код |

## Відкриті питання **[узгодити]**
1. Де зберігається маніфест (файл у репо, таблиця БД, адмінка) і хто його може змінювати.
2. Формат `source` (JSONPath чи власний синтаксис) і підтримка списків.
3. Чи реалізовуємо `executor` як HTTP-шаблон, чи дії виконує окремий адаптер (модуль Кирила / MCP).
4. Як виглядає `undo` для зовнішніх продуктів (компенсувальна дія з окремим описом).
5. Чи потрібна версія маніфесту в аудиті для кожного рішення.
6. Кількість власних передумов, які може додати tenant (рекомендація: жодної, лише стандартні).
