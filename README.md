# Warehouse_web

## Project overview
Warehouse_web — Django web-клиент складской системы. Приложение предоставляет UI для сотрудников и администраторов, а также управляет локальными справочниками (категории, единицы измерения, номенклатура) и доступом пользователей.

Проект интегрируется с внешним SyncServer API (FastAPI) через HTTP-клиент.

## Architecture overview
Система построена как многомодульный Django monolith (MVT) с ролевым доступом и шаблонным веб-интерфейсом:

- **Client/UI layer**: Django templates + function/class-based views.
- **Application/API layer**: URL routing и view-контроллеры в `apps/*/urls.py` и `apps/*/views.py`.
- **Service/Integration layer**: общие permission-функции и HTTP-клиент SyncServer.
- **Data layer**: Django ORM модели.
- **Database**: SQLite в текущей конфигурации.

## Tech stack
- Python 3
- Django 6
- Django ORM
- SQLite (default)
- httpx (интеграция с внешним API)
- Django Templates

## Project structure
```text
config/                 # настройки и маршрутизация проекта
apps/
  catalog/              # справочники склада: Category, Unit, Item
  users/                # роли, профили, login/logout, сигналы
  client/               # dashboard клиента
  documents/            # заготовка модуля документов
  common/               # permissions и общие сервисы
  integration/          # интеграция с SyncServer
templates/              # HTML шаблоны
manage.py               # entrypoint Django CLI
```

## Installation / Setup
1. Создать виртуальное окружение.
2. Установить зависимости проекта (Django, httpx).
3. Применить миграции.
4. Создать суперпользователя (опционально).

Пример команд:

```bash
python -m venv .venv
source .venv/bin/activate
pip install django httpx
python manage.py migrate
python manage.py createsuperuser
```

## Running the project
```bash
python manage.py runserver
```

По умолчанию приложение доступно на `http://127.0.0.1:8000/`.

## Main modules
- `apps/catalog` — CRUD справочников склада.
- `apps/users` — роли (`root`, `chief_storekeeper`, `storekeeper`), профиль и авторизация.
- `apps/client` — защищенный dashboard.
- `apps/common` — permission-правила и общий SyncServer клиент.
- `apps/integration` — интеграционный HTTP-клиент к SyncServer.
- `apps/documents` — будущий модуль документов (пока заготовка).

## API overview
Проект в первую очередь серверит HTML-страницы, а не публичный REST API. Основные маршруты:

- `/catalog/` — каталог и справочники.
- `/client/` — dashboard клиента.
- `/users/login/`, `/users/logout/` — авторизация.
- `/admin/` — Django admin.

