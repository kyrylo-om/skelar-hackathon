# Запуск усіх серверів

Команди виконуються з кореня репозиторію `skelar-hackathon`.
Це локальний демонстраційний запуск із синтетичним білінгом, Django runserver і Vite.
AI за замовчуванням працює в явно заданому **mock-режимі**, без зовнішніх API-викликів.
Поточна БД проєкту — SQLite; Docker зберігає її в named volumes.

## Docker Compose — рекомендований запуск

Потрібні Docker Engine/Desktop і Docker Compose v2 або новіший.
Під час першої збірки потрібен доступ до Docker Hub, PyPI та npm registry.

```bash
cp .env.example .env
docker compose up --build -d --wait
docker compose ps
```

Копіюйте `.env.example` лише під час першого налаштування; існуючий `.env` збережіть.
Root `.env` призначений для Compose. Локальний `backend/.env` не копіюється в image і не
використовується контейнерами. Ключі передаються лише потрібним Python-серверам;
frontend/widget отримують тільки адресу proxy.

Backend автоматично виконує `migrate`, `seed_demo`, `seed_tenants` перед запуском.
Повторний seed не скидає паролі, виконані дії та підписки.

| Сервер | URL на комп'ютері | Призначення |
| --- | --- | --- |
| Frontend | http://127.0.0.1:5173 | Кабінет клієнта та оператора |
| Backend | http://127.0.0.1:8000/api/health/ | Django REST API, перевірка готовності |
| Widget | http://127.0.0.1:5174/widget.js | Loader і React-чат у iframe |
| Execution | http://127.0.0.1:9000/mcp | MCP API для backend; не сторінка для браузера |
| CloudBox | http://127.0.0.1:9201 | Портал хмарного сховища з вбудованим чатом |
| ShopX | http://127.0.0.1:9202 | Портал магазину та API другого demo-продукту |

Відкривайте CloudBox через `127.0.0.1`: його HTML завантажує віджет із
`http://127.0.0.1:5174/widget.js`. Усі host-порти Compose прив'язані до loopback.
Зупиніть інші локальні процеси на цих портах перед запуском.

### Демонстраційні облікові записи

На frontend увійдіть як `paid_plus`, `active_pro`, `refund_review` або `operator`.
Спільний пароль новостворених акаунтів — значення `DEMO_PASSWORD` у root `.env`:
у прикладі `local-demo-password-2026`. Пароль має містити не менше 12 символів.
Поле пароля у формі може містити старий приклад — замініть його на `DEMO_PASSWORD`.
Зміна змінної не змінює вже створені паролі.

У CloudBox/ShopX виберіть клієнта зі списку та натисніть «Увійти»; це demo-вхід без пароля.

Для основного сценарію відкрийте CloudBox, виберіть `c-101` (Олена Коваль), відкрийте чат
і напишіть «Оплатив Plus, а тариф досі Free». Або увійдіть на frontend як `paid_plus`.
Backend працює через execution і змінює саме demo-БД CloudBox. Для передачі оператору
попросіть повернення коштів або розмову з людиною; оператор входить на frontend як `operator`.
Облікові записи frontend і вбудованого віджета мають окремі чати, але можуть посилатися
на того самого клієнта продукту.

### Керування

```bash
# Стан і логи
docker compose ps
docker compose logs -f backend execution
docker compose logs -f frontend widget cloudbox shopx

# Перезібрати після змін коду (source не змонтовано з host)
docker compose up --build -d --wait

# Зупинити зі збереженням даних
docker compose down

# Команда Django у запущеному backend
docker compose exec backend python manage.py check
```

Окремі volumes зберігають Django DB, CloudBox DB, ShopX DB і execution audit JSONL.
Proposals execution залишаються в пам'яті: перезапуск execution втрачає невиконані proposals;
для них потрібно почати нову пропозицію у чаті.

Для **навмисного видалення всіх контейнерних demo-даних** та повторного початку:

```bash
docker compose down --volumes
docker compose up -d --wait
```

Ця команда видаляє також користувачів, чати й audit log у volumes. Локальні SQLite-файли
поза Docker вона не зачіпає.

### Live AI

Поточний код реалізує `mock` та `deepseek`; Gemma/Gemini adapter у цьому запуску не додається.
Щоб використати вже наявний live adapter, задайте в root `.env` `LLM_PROVIDER=deepseek`,
власний `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, потім застосуйте конфігурацію:

```bash
docker compose up -d --wait backend
```

Live API може тарифікуватися провайдером. За відсутності ключа залиште `mock`.
`.env` і локальні бази виключені з build context через `.dockerignore`.

## Локально без Docker

Потрібні Python 3.14 (image використовує ту саму гілку), Node.js 24 і npm.
Використовуйте одну virtualenv у корені для backend, execution і mock-продуктів.

Початкове налаштування:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt -r execution/requirements-dev.txt -r mocks/requirements-dev.txt
npm --prefix frontend ci
npm --prefix widget ci
cp .env.example .env
```

Знову ж, існуючий `.env` не перезаписуйте. У **кожному Python-терміналі** з кореня виконайте:

```bash
source .venv/bin/activate
set -a
source .env
set +a
export DEBUG=True
export ORCHESTRATOR_GATEWAY=mcp
export EXECUTION_URL=http://127.0.0.1:9000
export WIDGET_SECRETS="cloudbox=$CLOUDBOX_WIDGET_SECRET,shopx=$SHOPX_WIDGET_SECRET"
```

Це root `.env` для спільних ключів. Django додатково читає `backend/.env`, якщо він є;
вже експортовані змінні мають пріоритет. Без власного `DATABASE_URL` Django використовує
`backend/db.sqlite3`. Для чистого локального SQLite запуску приберіть застарілий
`DATABASE_URL` із shell та `backend/.env`, якщо раніше налаштовували іншу БД.
У локальному запуску не задавайте Docker-адреси `http://execution:9000` або
`EXECUTION_PRODUCTS=/app/docker/products.toml`: за замовчуванням `execution/products.toml`
вже містить правильні loopback-адреси продуктів.

Одноразова підготовка Django після експорту змінних:

```bash
cd backend
python manage.py migrate
python manage.py seed_demo
python manage.py seed_tenants
cd ..
```

Запустіть **кожен сервер в окремому терміналі**, у такому порядку.
Для перших чотирьох терміналів спочатку виконайте спільний Python setup вище.

```bash
# Термінал 1, з кореня
python -m mocks.cloudbox
```

```bash
# Термінал 2, з кореня
python -m mocks.shopx
```

```bash
# Термінал 3, з кореня, після запуску обох продуктів
python -m execution
```

```bash
# Термінал 4, з кореня
cd backend
python manage.py runserver 127.0.0.1:8000
```

```bash
# Термінал 5, з кореня
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

```bash
# Термінал 6, з кореня
cd widget
npm run dev
```

URL і логіни такі самі, як у таблиці Docker. Завершуйте сервери через Ctrl+C.
`python -m mocks.cloudbox --reset` або `python -m mocks.shopx --reset` перебудовує відповідну
локальну mock-БД і видаляє її попередній demo-стан.

## Діагностика

```bash
# Перевірити Compose без запуску контейнерів
docker compose --env-file .env.example config --quiet

# Після старту
curl --fail http://127.0.0.1:8000/api/health/
curl --fail http://127.0.0.1:5173/api/health/
curl --fail http://127.0.0.1:5174/widget.js -o /dev/null
curl --fail http://127.0.0.1:9201/portal/customers
curl --fail http://127.0.0.1:9202/portal/customers
```

- `permission denied ... docker.sock`: поточний shell не має доступу до Docker daemon;
  перевірте свій Docker Engine/Desktop/rootless context і його права.
- `address already in use`: зупиніть попередній сервер на відповідному порту.
- `Invalid Host header` від MCP: у Compose `EXECUTION_ALLOWED_HOSTS` має дозволяти
  `execution:9000`. Захист DNS rebinding залишається ввімкненим.
- `CSRF failed`: відкривайте frontend через localhost/127.0.0.1:5173 і залиште API-запити
  через Vite proxy. CSRF не вимикається.
- `service ... unhealthy`: подивіться `docker compose logs <service>`; frontend/widget
  очікують готовності backend, backend — execution, execution — двох продуктів.
- `Could not find a version` / `ENOTCACHED` / DNS error під час build: перевірте доступ до
  package registry. Залежності залишені з наявними версіями та lockfiles.

Конфігурація Compose перевірена парсером. Фактичну збірку images і старт контейнерів у
середовищі Codex не підтверджено: доступ до Docker daemon заборонений.
