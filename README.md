# Warehouse_web

Warehouse_web is a **Django server-rendered client** for warehouse operators.
It provides UI/auth flows and depends on SyncServer for catalog master data.

> Core invariant: **SyncServer is the source of truth**. Warehouse_web must not directly read/write SyncServer PostgreSQL tables.

## Architecture

```text
Browser
  -> Django (Warehouse_web)
  -> CatalogService
  -> SyncServerClient (HTTP + device headers)
  -> SyncServer API
  -> PostgreSQL (owned by SyncServer)
```

Warehouse_web keeps only local client data (auth/sessions/admin-related) in its own Django DB.

## Configuration

Copy and edit environment file:

```bash
cp .env.example .env
```

Important variables:
- Django runtime/security: `DJANGO_ENV`, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
- Local Django DB: `DB_ENGINE`, `DB_NAME`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`
- SyncServer integration: `SYNC_SERVER_URL`, `SYNC_SITE_ID`, `SYNC_DEVICE_ID`, `SYNC_DEVICE_TOKEN`, `SYNC_CLIENT_VERSION`, `SYNC_SERVER_TIMEOUT`

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Pages:
- `/users/login/`
- `/client/`
- `/catalog/categories/`
- `/catalog/units/`
- `/catalog/items/`

## Production mode (without Docker)

```bash
export DJANGO_ENV=production
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60
```

## Docker run

```bash
docker compose up --build
```

Container entrypoint runs `migrate` and `collectstatic`, then starts Gunicorn.

## SyncServer connectivity checks
- App health: `GET /healthz/`
- Sync dependency health: `GET /healthz/sync/`

If SyncServer is unavailable, catalog pages show a readable Django message and remain renderable with empty-state tables.

## More docs
- Deployment operations: [DEPLOYMENT.md](DEPLOYMENT.md)
- Architecture decision records: `docs/adr/`
