# DEPLOYMENT

This document describes realistic deployment requirements for **Warehouse_web** as a Django client application that depends on **SyncServer**.

## 1) System role and dependency
- Warehouse_web is a UI/client layer.
- SyncServer is the source of truth for catalog data.
- Warehouse_web must communicate with catalog through SyncServer HTTP API only.

## 2) Required environment variables
Current codebase reads Sync variables from `.env` (`config/settings.py`).

Required in production-like environments:

```env
# Django (recommended to externalize)
SECRET_KEY=<strong-secret>
DEBUG=False
ALLOWED_HOSTS=your-domain,internal-host

# SyncServer connectivity (required)
SYNC_SERVER_URL=https://syncserver.example.com
SYNC_SITE_ID=<uuid>
SYNC_DEVICE_ID=<uuid>
SYNC_DEVICE_TOKEN=<registration-token>
SYNC_CLIENT_VERSION=warehouse-web/1.0
SYNC_SERVER_TIMEOUT=10
```

> Note: in current code, `SECRET_KEY`, `DEBUG`, and `ALLOWED_HOSTS` still have development defaults and are not fully env-driven yet. Treat this as a hardening gap before production.

## 3) Startup sequence
1. Ensure SyncServer bootstrap entities exist (`site`, `device`, registration token).
2. Configure `.env` with Sync identifiers and token.
3. Run database migrations for local Django data:
   ```bash
   python manage.py migrate
   ```
4. (Optional) create administrative user:
   ```bash
   python manage.py createsuperuser
   ```
5. Collect static assets (once STATIC_ROOT is configured):
   ```bash
   python manage.py collectstatic --noinput
   ```
6. Start application server (`runserver` for dev; Gunicorn/ASGI server for production setup).

## 4) Static files status
Current settings define:
- `STATIC_URL = 'static/'`
- `STATICFILES_DIRS = [BASE_DIR / 'static']`

Current settings do **not** define `STATIC_ROOT`, so production `collectstatic` pipeline is incomplete.

## 5) Application server and containerization status
Current repository state:
- No `Dockerfile`
- No `docker-compose.yml`
- No checked-in Gunicorn configuration

Operational implication:
- Deployment artifacts must be added externally or in a dedicated infra PR.

## 6) SyncServer failure behavior (current)
- HTTP calls use `httpx` with timeout from `SYNC_SERVER_TIMEOUT`.
- Connection issues raise user-facing error "SyncServer временно недоступен.".
- Catalog service maps common status codes (400/404/409/5xx) to predictable UI messages.

## 7) Post-deploy validation checklist
- Login works at `/users/login/`.
- Dashboard opens at `/client/`.
- Catalog pages open:
  - `/catalog/categories/`
  - `/catalog/units/`
  - `/catalog/items/`
- Validate SyncServer connectivity by checking category/unit/item lists load.
- Validate error handling by temporarily pointing `SYNC_SERVER_URL` to an invalid host and confirming readable error messages.

## 8) Known production gaps in current codebase
- Settings are not yet split into dedicated development/production modules.
- Security-critical Django settings are not fully environment-driven.
- Static pipeline lacks `STATIC_ROOT`.
- Production runtime stack files (Gunicorn/Docker/Nginx) are absent.

This repository is close to functionally integrated state, but requires these hardening items before true production deployment.
