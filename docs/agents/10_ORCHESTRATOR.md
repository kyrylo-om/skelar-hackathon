# 10. Оркестратор: одне повідомлення клієнта від входу до відповіді

Статус: реалізовано в `backend/apps/orchestrator` для домену хмарного сховища (`apps/subscriptions`
і `apps/support` з `dev`). Пункти **[узгодити]** ще не підтверджені командою.

## Призначення
Закриває проблему «агенти є, а повідомлення клієнта ніхто через них не проводить»: бере повідомлення з чату,
проганяє його через Guard, Triage, Actor, Critic і Policy, виконує дозволену дію або передає людині й
повертає чесну відповідь. Жодна відповідь моделі не потрапляє в продукт повз Gate і шлюз.

## Де він у системі

```
чат клієнта (React)
   │  POST /api/review/my/chat/messages/
   ▼
apps/review  receive_customer_message ─► ports.run_pipeline
   │                                          │ ORCHESTRATOR_ENABLED
   ▼                                          ▼
 Chat, Message, TraceStep, ReviewItem   apps/orchestrator.handle_customer_message
                                              │
              ┌───────────────────────────────┼─────────────────────────┐
              ▼                               ▼                         ▼
        apps/security                  facts.py (читає продукт)   gateway.py (пише в продукт)
        Guard, Triage, Actor,          apps/subscriptions          apps/support services:
        Critic, Policy, Gate,          (лише читання)              begin_turn, propose_*, record_review,
        router + llm                                               execute_sync, finish_turn
```

Оператор схвалює через кабінет: `decide_review` ─► `ports.execute` ─► `execute_approved`, де Policy
ще раз перевіряє дію в режимі `after_human_approval`.

## Алгоритм (`pipeline._run`)

| № | Крок | Що відбувається | Якщо збій |
|---|---|---|---|
| 1 | **Guard** (`screen_input`) | правила, маскування PII, LLM лише для сумнівного | `block`, відповідь-відмова, `SecurityEvent` |
| 2 | Чат уже в черзі людини? | не запускає агентів вдруге | відповідь «передано спеціалісту», нового review немає |
| 3 | Факти | `facts.load_facts` і `policy_ctx` з БД продукту | — |
| 4 | **Triage** | інтент, сентимент, пріоритет; валідація й нижні межі | недійсне або впевненість < 0.6 дає `unclear` |
| 5 | Службові інтенти | `smalltalk`, `out_of_scope` відповідаються шаблоном без Actor | — |
| 6 | Лише-людські інтенти | `legal_threat`, `account_deletion`, `payment_method_change` та юридичні слова | review без Actor |
| 7 | `unclear` | одне уточнення (макс. 2 поспіль), потім людина | review `clarification limit` |
| 8 | **Actor** | план JSON з дозволених для інтенту дій | недійсний або недоступний: повтор, потім review |
| 9 | Перевірка плану (`plan.validate_plan`) | дії з маніфесту, ідентифікатори лише з фактів клієнта, без `customer_id`, одна змінна дія | помилки йдуть Actor як зворотний зв'язок |
| 10 | **Critic** | незалежний вердикт без `reasoning` Actor | `reject`: Actor переробляє (до 2 разів); `needs_human`: review |
| 11 | **Policy** (по кожній дії) | власник, платіж підтверджений, статус, ліміти, rate limit, повтор | `deny` дає відмову, `needs_review` дає review |
| 12 | **Gate** | найсуворіший вердикт: `block` > `review` > `execute` | — |
| 13 | **Виконання** | шлюз: `sync_subscription`, `cancel_auto_renewal`, читання | помилка: чесна відповідь і review |
| 14 | Відповідь | шаблон із реальних результатів; LLM-переписування лише якщо ввімкнено й безпечне | шаблон |

Увесь прохід в межах `message_budget()`: не більше `LLM_MAX_CALLS_PER_MESSAGE` викликів моделі на повідомлення.
Вичерпання ліміту дає безпечні дефолти (Triage `unclear`, Actor недоступний, Critic `needs_human`).

## Рішення та їх наслідки

| Рішення | Коли | Відповідь клієнту | Побічні ефекти |
|---|---|---|---|
| `execute` | усе пройшло | з результатів дії | дія в продукті, `ActionLog`, аудит, лічильник уточнень скинуто |
| `execute` (скасування) | `cancel_auto_renewal` | «натисніть Підтвердити» | дія в стані `awaiting_confirmation`, кнопка в чаті |
| `review` | Policy `needs_review`, Critic `needs_human`, лише-людські інтенти, збої | «передав спеціалісту» | `ReviewItem` у черзі, `Chat.status=needs_review`, підсумок для оператора |
| `block` | атака або Policy `deny` | відмова без причин | `SecurityEvent` для атак |
| `clarify` | неясний запит, питання Actor, small talk | одне питання | лічильник уточнень |
| `busy` | у клієнта вже йде хід | «повторіть за хвилину» | нічого не змінюється |

## Модулі

| Файл | Роль |
|---|---|
| `pipeline.py` | алгоритм, `handle_customer_message`, `execute_approved`, `pending_confirmation` |
| `manifest.py` | дії, інтенти, пороги ескалації, шаблони відповідей (домен CloudBox); валідується при імпорті проти реєстру Policy |
| `facts.py` | `load_facts` для Actor/Critic і `policy_ctx` для Policy, лише читання |
| `plan.py` | детерміновані перевірки плану Actor |
| `gateway.py` | `DevDomainGateway`: єдиний шлях запису в продукт |
| `responder.py` | тексти відповідей, безпечне LLM-переписування |
| `models.py` | `TurnState`: лічильник уточнень і останній інтент для чату |

## Безпека виконання (`gateway.py`)
- Дії проходять через довірені сервіси `apps/support`: ходи з токеном, версіями й оренду (lease), ідемпотентність.
  `Conversation` тут лише прихований журнал дій; чат клієнта живе в `apps/review`.
- Модель ніколи не бачить токена, версій і ідентифікаторів сесії.
- Скасування автопродовження не виконується з чату: `confirm_cancellation` викликає лише автентифікований
  ендпоінт `/api/actions/{id}/confirm/` (кнопка клієнта), тож «так» у тексті нічого не підтверджує.
- Після схвалення оператором Policy перевіряє дію ще раз зі свіжими фактами (власник, платіж, статус).
  Якщо стан змінився: `ExecutionError`, дія лишається `pending`.

## Налаштування

| Змінна | Типово | Значення |
|---|---|---|
| `ORCHESTRATOR_ENABLED` | `True` | вимкнено: кожне повідомлення просто передається людині |
| `ORCHESTRATOR_LLM_RESPONDER` | `False` | чи просити модель переписати шаблонну відповідь |
| `LLM_PROVIDER` | `mock` | `deepseek` для справжньої моделі, `mock` без ключа |
| `LLM_MAX_CALLS_PER_MESSAGE` | `6` | ліміт викликів моделі на повідомлення |
| `DAILY_REFUND_LIMIT`, `AUTO_REFUND_LIMIT`, `HARD_REFUND_LIMIT`, `RISKY_ACTIONS_PER_HOUR`, `IDEMPOTENCY_WINDOW_SEC` | див. `settings.py` | пороги Policy |

## Що тестується
`apps/orchestrator/tests`: сценарії від чату до продукту (активація, статус, скасування з підтвердженням, повернення, юридична
погроза, атака, неясні запити з лімітом уточнень), збої моделі (сміття, недоступний Actor, Critic, що відхиляє,
вичерпаний бюджет, зайнятий хід), чужі ідентифікатори й чужі підтвердження, виконання після схвалення з повторною
перевіркою Policy, перевірка плану, маніфест, безпечність відповіді. Усі працюють на mock без мережі.

## Чого ще немає **[узгодити]**
1. **MCP.** `ORCHESTRATOR_GATEWAY=mcp` вмикає `McpGateway` (`mcp_gateway.py`): факти й дії йдуть через наш
   сервер виконання (`execution/`) до зовнішнього продукту (мок `mocks/cloudbox`). Дія спершу пропонується й
   виконується лише після Gate або кнопки клієнта; деталі в `execution/README.md`. Лишилось: мапінг дій на виклики
   API (`CALLS`) і полів фактів зараз написаний для CloudBox у коді, а не в маніфесті (`executor`, `entities`).
2. **Підтримані дії.** Шлюз знає `get_subscription`, `get_payments`, `sync_subscription`, `cancel_auto_renewal`. Повернення,
   пауза тощо потребують підтримки продукту; їх схвалення людиною зараз закінчується `ExecutionError`.
3. **Маніфест у YAML/БД** замість Python-структури, і читання реєстру дій Policy з нього.
4. **Контекст розмови.** Actor бачить лише останнє повідомлення, факти й лічильники (немає історії діалогу), а
   `pending_action` у контексті завжди `null`.
5. **Живий тест моделі.** Оркестратор перевірено на mock; поведінку на DeepSeek покаже `scripts/check_llm.py` із ключем.
6. **Чи Triage й Actor лишаються двома викликами**, бюджет часу (30 с з `docs/BACKEND.md`) і метрика «заблоковано N із N».
