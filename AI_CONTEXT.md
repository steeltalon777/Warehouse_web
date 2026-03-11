# AI_CONTEXT

## System architecture
Warehouse_web — Django MVT web-клиент. Основная цель: UI и управление справочниками/доступом, плюс интеграция с внешним SyncServer API.

## Backend rules
- Бизнес-правила доступа должны проходить через `apps/common/permissions.py`.
- View-слой должен оставаться тонким: обработка запроса, проверка прав, делегирование в ORM/сервисы.
- Интеграции с внешними API должны идти через выделенные клиенты в `apps/common/services` или `apps/integration`.

## Database rules
- Использовать Django ORM и модели в соответствующих app-модулях.
- Для доменных сущностей каталога использовать UUID PK (как в текущих моделях).
- Сохранять целостность ссылок через `on_delete` политики (`SET_NULL`, `PROTECT`, `CASCADE`).
- Валидации целостности (например, без циклов в дереве категорий) держать в модели.

## Layered architecture
### API
- `config/urls.py`, `apps/*/urls.py`, `apps/*/views.py`.

### Services
- `apps/common/permissions.py`
- `apps/common/services/*`
- `apps/integration/*`

### Repositories
- Явный repository-слой не выделен; доступ к данным идет через ORM внутри views/models.

### Models
- `apps/catalog/models.py`
- `apps/users/models.py`

## Client rules
- Основной клиент: браузер через Django templates.
- Административный клиент: Django admin.
- Внешний системный клиент: SyncServer API (HTTP).

## Architecture constraints
- Не смешивать role checks по проекту: использовать общие функции `can_*`.
- Не добавлять прямые raw SQL без необходимости.
- Не дублировать интеграционный код; новые внешние вызовы оформлять через единый адаптер.
- `apps/documents` пока заготовка; не предполагать завершенную бизнес-логику документов.
