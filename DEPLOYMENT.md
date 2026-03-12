# DEPLOYMENT

This document covers deployment of **Warehouse_web** as a Django client that depends on **SyncServer**.

## 1. System role (must preserve)
- Warehouse_web = web client/UI + auth.
- SyncServer = source of truth for catalog data.
- Catalog data flow is only via SyncServer HTTP API.
- Warehouse_web must not directly access SyncServer PostgreSQL.

## 2. Required environment variables
Use `.env.example` as baseline.

### Django
- `DJANGO_ENV` (`development` or `production`)
- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`

### Django local DB (client-side data only)
- `DB_ENGINE`
- `DB_NAME`
- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_CONN_MAX_AGE`

### SyncServer integration (required)
- `SYNC_SERVER_URL`
- `SYNC_SITE_ID`
- `SYNC_DEVICE_ID`
- `SYNC_DEVICE_TOKEN`
- `SYNC_CLIENT_VERSION`
- `SYNC_SERVER_TIMEOUT`

### Production hardening
- `SECURE_SSL_REDIRECT`

## 3. Startup sequence
1. Ensure SyncServer bootstrap exists (`site`, `device`, registration token).
2. Configure `.env` in deployment environment.
3. Start app with production settings (`DJANGO_ENV=production`).
4. Run migrations:
   ```bash
   python manage.py migrate --noinput
   ```
5. Build static:
   ```bash
   python manage.py collectstatic --noinput
   ```
6. Run Gunicorn:
   ```bash
   gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60
   ```

## 4. Static pipeline
- `STATIC_URL=/static/`
- `STATIC_ROOT=<repo>/staticfiles`
- `STATICFILES_DIRS=<repo>/static`
- Production uses WhiteNoise `CompressedManifestStaticFilesStorage`.

## 5. Containerized deployment
Included artifacts:
- `Dockerfile`
- `docker-compose.yml`
- `entrypoint.sh`

Run:
```bash
docker compose up --build
```

The entrypoint runs `migrate` + `collectstatic` before executing Gunicorn command.

## 6. Health and diagnostics
- Liveness: `GET /healthz/`
- Sync dependency: `GET /healthz/sync/`
  - `200` when SyncServer catalog API responds.
  - `503` with reason when dependency fails.

## 7. Post-deploy verification
1. Login works at `/users/login/`.
2. Dashboard opens at `/client/`.
3. Catalog pages render:
   - `/catalog/categories/`
   - `/catalog/units/`
   - `/catalog/items/`
4. Confirm `/healthz/sync/` reports healthy.
5. Temporarily break `SYNC_SERVER_URL` to confirm graceful UI error messaging.

## 8. Common failure points
- Missing/invalid Sync bootstrap identifiers (`SYNC_SITE_ID`, `SYNC_DEVICE_ID`, `SYNC_DEVICE_TOKEN`).
- `ALLOWED_HOSTS` not matching ingress host.
- Not running `collectstatic` in production.
- SyncServer network reachability / TLS mismatch.

## Docker deployment with nginx gateway

Warehouse_web обычно запускается вместе с SyncServer за reverse proxy (nginx).

### Архитектура


Browser
↓
nginx gateway
↓
Warehouse_web (Django)
↓
SyncServer (FastAPI)
↓
PostgreSQL


### Подготовка

Создать внешнюю docker сеть:

```bash
docker network create backend
Запуск SyncServer
cd SyncServer
docker compose up -d --build
Запуск Warehouse_web
cd Warehouse_web
docker compose up -d --build
Запуск nginx gateway
cd gateway
docker compose up -d
Проверка

Открыть:

http://<server-ip>/

Должен произойти редирект:

/ → /client/

Проверить:

/client/
/admin/
/api/
/api/docs
Переменные окружения

Пример:

SYNC_SERVER_URL=http://syncserver:8000
SECURE_SSL_REDIRECT=False
CSRF_TRUSTED_ORIGINS=http://<server-ip>
Важно

В Docker контейнере localhost указывает на сам контейнер, а не на хост.

Поэтому SyncServer должен вызываться через имя сервиса:

http://syncserver:8000
HTTPS

После появления домена nginx должен выполнять TLS termination.

После этого можно включить:

SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

---

# Вставка для `ARCHITECTURE.md`

Добавь раздел **Ingress layer**.

```md
## Ingress layer

В production доступ к Warehouse_web осуществляется через nginx reverse proxy.


Browser
↓
nginx
↓
Warehouse_web
↓
SyncServerClient
↓
SyncServer API


### Причины использования reverse proxy

- единая точка входа
- TLS termination
- проксирование `/api/` в SyncServer
- корректная работа CSRF и Host заголовков