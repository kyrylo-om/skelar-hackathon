# Project

Django + React template.

| Part       | Stack                                    |
|------------|------------------------------------------|
| `backend/` | Django 6, Django REST Framework, SQLite  |
| `frontend/`| React 19, TypeScript, Vite, Vitest       |

## Getting started

Requires Python 3.12+ and Node 20.19+.

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Frontend (in another terminal):

```bash
cd frontend
npm install
npm run dev
```

- App: http://localhost:5173
- API: http://localhost:5173/api/ (proxied to Django on :8000)
- Admin: http://localhost:5173/admin/ (create a user with `python manage.py createsuperuser`)

Vite proxies `/api`, `/admin` and `/static` to `BACKEND_URL` (default `http://localhost:8000`),
so the frontend and API share an origin and session auth + CSRF work without CORS.

## Tests and linting

```bash
cd backend && pytest && ruff check . && ruff format --check .
cd frontend && npm test && npm run lint && npm run build
```

## Project layout

```
backend/
  config/            # settings, root urls, wsgi/asgi
  apps/
    core/            # health check; template for new apps
frontend/
  src/
    api/client.ts    # fetch wrapper (JSON, cookies, CSRF, ApiError)
    App.tsx
```

## Extending

**New backend app**

```bash
cd backend
mkdir apps/<name> && python manage.py startapp <name> apps/<name>
```

Then set `name = "apps.<name>"` in `apps/<name>/apps.py`, add `"apps.<name>"` to
`INSTALLED_APPS`, and include its urls in `config/urls.py` under `api/`.

**Calling the API from React**

```ts
import { api } from './api/client'

const items = await api.get<Item[]>('/items/')
await api.post('/items/', { title: 'New' })
```

**Configuration** is read from environment variables (see `backend/.env.example`).
The API requires authentication by default (`IsAuthenticated`); open individual
endpoints with `permission_classes([AllowAny])` as in `apps/core/views.py`.

Cloud Support backend implementation, synthetic-account setup, verification limits and
AI integration contract: [docs/BACKEND.md](docs/BACKEND.md).
