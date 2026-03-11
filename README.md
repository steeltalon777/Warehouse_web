# Warehouse_web

Warehouse_web — Django SSR-приложение для сотрудников склада. Приложение предоставляет UI, авторизацию и ролевой доступ, а каталог номенклатуры получает и изменяет через внешний SyncServer API.

## Project overview
- Назначение: web-клиент для складских операций и управления справочниками каталога.
- Важное ограничение: `Category`, `Unit`, `Item` в этом репозитории не являются source of truth; изменения выполняются через SyncServer.

## Architecture overview
```text
Browser
  ↓
Django views + templates (Warehouse_web)
  ↓
CatalogService
  ↓
SyncServerClient (httpx)
  ↓ HTTP + X-* headers
SyncServer API
```

## Tech stack
- Python 3
- Django 6 (SSR, auth, admin)
- Django Templates
- httpx (интеграция с SyncServer)
- SQLite (локальные Django-данные: auth/sessions/admin и локальные модели)

## Project structure
- `config/` — settings, корневые URL, ASGI/WSGI
- `apps/catalog/` — UI каталога: views/forms/services/models
- `apps/integration/` — HTTP-клиент SyncServer
- `apps/users/` — auth-профили, роли, site
- `apps/common/` — permission-функции
- `apps/client/` — dashboard
- `apps/documents/` — заготовка модуля документов
- `templates/` — SSR шаблоны
- `docs/adr/` — архитектурные решения

## Installation / Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # если отсутствует: pip install django httpx
python manage.py migrate
```

## Running the project
```bash
python manage.py runserver
```

Нужные переменные окружения для SyncServer:
- `SYNC_SERVER_URL`
- `SYNC_SITE_ID`
- `SYNC_DEVICE_ID`
- `SYNC_DEVICE_TOKEN`
- `SYNC_CLIENT_VERSION`
- `SYNC_SERVER_TIMEOUT`

## Main modules
- `apps/catalog/views.py` — web-endpoints каталога (list/create/update/deactivate)
- `apps/catalog/services.py` — сервисный слой + mapping ошибок внешнего API
- `apps/integration/syncserver_client.py` — низкоуровневый HTTP клиент
- `apps/common/permissions.py` — правила доступа по роли
- `apps/users/models.py` — `Site`, `UserProfile`, роли

## API overview
- Внутренний HTTP интерфейс Django: `/catalog/*`, `/client/*`, `/users/*`, `/admin/`.
- Внешняя интеграция: вызовы SyncServer endpoint-ов:
  - `GET /catalog/categories`, `/catalog/categories/tree`, `/catalog/units`, `/catalog/items`
  - `POST/PATCH /catalog/admin/categories|units|items`
