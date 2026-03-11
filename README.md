# Warehouse_web

Warehouse_web — Django web-client для складской системы, где **SyncServer является единственным source of truth** по мастер-данным каталога (Category, Unit, Item).

## Project overview
- Warehouse_web отвечает за web UI, шаблоны, формы, авторизацию и роли.
- SyncServer (FastAPI) отвечает за хранение и изменение мастер-данных склада.
- Каталог в Warehouse_web работает через HTTP API SyncServer, а не через локальный ORM CRUD.

## Architecture overview
```text
Warehouse_web (Django UI)
        ↓ HTTP (X-Site-Id / X-Device-Id / X-Device-Token / X-Client-Version)
SyncServer (FastAPI source of truth)
        ↓
PostgreSQL
```

## Tech stack
- Python 3, Django 6
- Django Templates (SSR)
- httpx (HTTP integration)
- SQLite локально для Django-специфичных данных (users/sessions/admin)

## Project structure
```text
config/                          # settings, root urls, wsgi/asgi
apps/catalog/                    # catalog UI/views/forms/services (через SyncServer)
apps/integration/syncserver_client.py  # единый SyncServer client
apps/common/                     # permissions и shared utilities
docs/adr/                        # architecture decision records
templates/                       # HTML templates
```

## Setup / Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install django httpx
python manage.py migrate
python manage.py runserver
```

## SyncServer integration settings
Укажите переменные окружения:
- `SYNC_SERVER_URL`
- `SYNC_SITE_ID`
- `SYNC_DEVICE_ID`
- `SYNC_DEVICE_TOKEN`
- `SYNC_CLIENT_VERSION`
- `SYNC_SERVER_TIMEOUT`

Warehouse_web использует **статический system device** как trusted client SyncServer.

## Main modules
- `apps/catalog/views.py` — catalog pages через integration service.
- `apps/catalog/forms.py` — input forms с базовой валидацией.
- `apps/catalog/services.py` — orchestration + mapping ошибок SyncServer.
- `apps/integration/syncserver_client.py` — единый HTTP client.
