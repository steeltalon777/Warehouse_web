# INDEX

## Project Overview

**Warehouse_web** — Django web-клиент складской системы.

Основной backend системы — **SyncServer (FastAPI)**. Django-часть выполняет роль UI-клиента и административного интерфейса.

---

## Tech Stack

- Python
- Django
- HTML Templates

---

## Main Applications

- `apps/catalog` — справочники склада (категории, единицы измерения, ТМЦ)
- `apps/users` — управление пользователями и ролями
- `apps/common` — общие компоненты (permissions, сервисы)
- `apps/integration` — интеграция с SyncServer

---

## Catalog App Map

- `apps/catalog/models.py`
  - `Category` — дерево категорий
  - `Unit` — единицы измерения
  - `Item` — складские позиции
- `apps/catalog/views.py` — CRUD для справочников
- `apps/catalog/forms.py` — Django формы
- `apps/catalog/urls.py` — маршруты каталога
- `templates/catalog/` — UI-страницы каталога

---

## Entry Points

- `manage.py`
- `config/settings.py`
- `config/urls.py`

---

## Future Modules

- operations
- warehouse balances
- document templates
- API integration with SyncServer
