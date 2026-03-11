# Warehouse_web

Warehouse_web is a Django server-rendered client for warehouse staff. It provides UI, authentication, and role-based access, while warehouse catalog master data is fetched and changed through **SyncServer HTTP API**.

> Architectural invariant: **SyncServer is the source of truth**. Warehouse_web must not write catalog master data directly to SyncServer PostgreSQL.

## Project overview
- Purpose: operational web client for warehouse users.
- Role in system: client application in a multi-repository architecture.
- Source of truth split:
  - Warehouse_web DB: local app/auth data.
  - SyncServer DB: canonical catalog domain data.

## Architecture overview
```text
Browser
  ↓
Django Views + Templates (Warehouse_web)
  ↓
CatalogService
  ↓
SyncServerClient (httpx)
  ↓ HTTP (X-Site-Id, X-Device-Id, X-Device-Token, X-Client-Version)
SyncServer API
  ↓
PostgreSQL (behind SyncServer)
```

## Tech stack
- Python 3
- Django 6 (SSR + auth + admin)
- Django Templates
- httpx (SyncServer integration)
- python-dotenv (.env loading)
- SQLite by default for local Django data

## Project structure
- `config/` — settings, root routing, ASGI/WSGI entrypoints.
- `apps/catalog/` — catalog pages/forms/services/models.
- `apps/integration/` — SyncServer HTTP client wrapper.
- `apps/users/` — authentication profile + role domain.
- `apps/common/` — shared permissions and helpers.
- `apps/client/` — user dashboard pages.
- `apps/documents/` — documents module scaffold.
- `templates/` — server-rendered UI templates.
- `docs/adr/` — architectural decision records.

## Installation / Setup (local)
```bash
python -m venv .venv
source .venv/bin/activate
pip install django httpx python-dotenv
python manage.py migrate
python manage.py createsuperuser  # optional
```

## Environment configuration
Current settings are read from `.env` via `python-dotenv`.

Minimal example:
```env
# Django
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# SyncServer integration
SYNC_SERVER_URL=http://127.0.0.1:8001
SYNC_SITE_ID=<uuid-from-sync-bootstrap>
SYNC_DEVICE_ID=<uuid-from-sync-bootstrap>
SYNC_DEVICE_TOKEN=<registration-token-from-sync-bootstrap>
SYNC_CLIENT_VERSION=warehouse-web/1.0
SYNC_SERVER_TIMEOUT=10
```

## Running the project
```bash
python manage.py runserver 0.0.0.0:8000
```

Then open:
- `/users/login/` for login.
- `/client/` for dashboard.
- `/catalog/categories/`, `/catalog/units/`, `/catalog/items/` for catalog UI.

## Deployment notes
- This repository currently contains **no Dockerfile / docker-compose / gunicorn config**.
- For deployment checklist and operational steps, see [DEPLOYMENT.md](DEPLOYMENT.md).

## API overview
Internal web routes:
- `/catalog/*`
- `/client/*`
- `/users/*`
- `/admin/`

External SyncServer calls used by current catalog service:
- `POST /catalog/categories`
- `POST /catalog/units`
- `POST /catalog/items`
- `GET /catalog/categories/tree`
- `POST /catalog/admin/categories`, `PATCH /catalog/admin/categories/{id}`
- `POST /catalog/admin/units`, `PATCH /catalog/admin/units/{id}`
- `POST /catalog/admin/items`, `PATCH /catalog/admin/items/{id}`
