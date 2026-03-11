# Warehouse_web

## Project overview
Warehouse_web is a Django server-rendered web client for warehouse staff. It provides authentication, role-based access, and catalog UI workflows while delegating catalog master-data operations to an external SyncServer API.

## Architecture overview
The project is a modular Django monolith with explicit layering:

`Browser -> Django Views -> CatalogService -> SyncServerClient (HTTP) -> SyncServer API -> PostgreSQL`

Warehouse_web keeps its own local Django database for application concerns (users, sessions, admin, local app data), while SyncServer remains the source of truth for catalog master data.

## Tech stack
- Python 3
- Django 6
- Django Templates (SSR)
- httpx
- python-dotenv
- Gunicorn + WhiteNoise (production)
- SQLite by default (or PostgreSQL via env settings)

## Project structure
- `config/` — project settings and root URL/WSGI/ASGI wiring
- `apps/catalog/` — catalog UI, forms, service orchestration
- `apps/integration/` — SyncServer HTTP client
- `apps/users/` — roles, user profile extension, auth routing
- `apps/common/` — shared permissions and health checks
- `apps/client/` — main dashboard
- `apps/documents/` — reserved module scaffold
- `templates/` — server-rendered HTML templates
- `docs/adr/` — architecture decision records

## Installation / Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
```

## Running the project
Development:
```bash
python manage.py runserver 0.0.0.0:8000
```

Production-like (without Docker):
```bash
export DJANGO_ENV=production
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60
```

Docker:
```bash
docker compose up --build
```

## Main modules
- Catalog management UI (`/catalog/*`)
- User authentication and role access (`/users/*`)
- Warehouse dashboard (`/client/`)
- Health checks (`/healthz/`, `/healthz/sync/`)

## API overview
Warehouse_web mainly serves SSR pages. Integration API usage is outbound:
- Reads: SyncServer catalog list/tree endpoints
- Writes: SyncServer admin catalog endpoints
- Mandatory headers: `X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`

Internal HTTP routes are composed in Django URL configs (`config/urls.py` + app urls).
