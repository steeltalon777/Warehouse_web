# DEPLOYMENT

## 1) Roles in distributed system
- **Warehouse_web (Django):** web/admin client and technical auth layer.
- **SyncServer (FastAPI):** source of truth for users/roles/sites/catalog/balances/operations/devices/events.

## 2) Database separation
- Django uses a **separate service PostgreSQL DB** for auth/session/admin/service data.
- SyncServer uses a **separate domain DB/schema**.
- Django must not use sqlite in production.

## 3) Required env for Django production DB
- `DB_ENGINE` (must be PostgreSQL backend)
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `DB_CONN_MAX_AGE`

## 4) Sync integration env
- `SYNC_SERVER_URL` (inside docker network: `http://syncserver:8000`)
- `SYNC_SITE_ID`
- `SYNC_DEVICE_ID`
- `SYNC_DEVICE_TOKEN`
- `SYNC_CLIENT_VERSION`
- `SYNC_SERVER_TIMEOUT`

## 5) Production startup
```bash
export DJANGO_ENV=production
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60
```

## 6) Deployment guardrails
- Do not bind Django directly to SyncServer DB.
- Do not re-introduce domain users/roles/sites as Django source-of-truth entities.
- Keep API-first orchestration through SyncServer client/service layer.
