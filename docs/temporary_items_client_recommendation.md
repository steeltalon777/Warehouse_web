# Рекомендации по внедрению временных ТМЦ в `Warehouse_web`

## Цель

Подготовить Django-клиент `Warehouse_web` к полноценной работе с временными ТМЦ, которые уже реализованы на стороне `SyncServer`.

Документ фиксирует:

- что уже гарантирует сервер;
- какие места в клиенте сейчас несовместимы с этим сценарием;
- какую архитектуру внедрения стоит выбрать;
- какой минимальный объём работ нужен для первой рабочей поставки;
- что лучше делать второй очередью.

---

## Что уже есть на стороне `SyncServer`

Сервер уже поддерживает полный базовый цикл временных ТМЦ:

- `GET /api/v1/temporary-items`
- `GET /api/v1/temporary-items/{temporary_item_id}`
- `GET /api/v1/temporary-items/{temporary_item_id}/operations`
- `POST /api/v1/temporary-items/{temporary_item_id}/approve-as-item`
- `POST /api/v1/temporary-items/{temporary_item_id}/merge`

Также сервер уже расширил DTO операций:

- строка операции может содержать `temporary_item_id`;
- строка операции может содержать `temporary_item_status`;
- строка операции может содержать `resolved_item_id` и `resolved_item_name`;
- строка операции уже несёт snapshot-поля:
  - `item_name_snapshot`
  - `item_sku_snapshot`
  - `unit_name_snapshot`
  - `unit_symbol_snapshot`
  - `category_name_snapshot`

Критическое серверное правило:

- если в операции есть inline temporary item, клиент обязан передать `client_request_id`;
- внутри строки вместо `item_id` можно передать объект `temporary_item`;
- история операции не должна переписываться после approve/merge;
- модерация временных ТМЦ доступна только `chief_storekeeper` или `root` с правом управления каталогом.

Пример payload, который клиент должен уметь собирать:

```json
{
  "operation_type": "RECEIVE",
  "site_id": 1,
  "client_request_id": "7e31b0ee-f7b3-4fb6-b7a8-4d31ab6d89fb",
  "lines": [
    {
      "line_number": 1,
      "item_id": 101,
      "qty": "3"
    },
    {
      "line_number": 2,
      "temporary_item": {
        "client_key": "tmp-2",
        "name": "Кабель контрольный 4х1.5",
        "sku": "TMP-CABLE-4X15",
        "unit_id": 3,
        "category_id": 7,
        "description": "Опознание требует проверки"
      },
      "qty": "2"
    }
  ]
}
```

---

## Что сейчас не готово в `Warehouse_web`

### 1. Форма создания операции умеет только постоянные ТМЦ

Сейчас `apps/operations/views.py` в `_build_create_payload()` собирает строки только как:

- `item_id`
- `qty`

Поддержки `temporary_item` и `client_request_id` нет.

### 2. Inline create в операции сейчас создаёт постоянную ТМЦ

Сейчас `OperationItemCreateView` в `apps/operations/views.py` использует `CatalogService.create_item()`.

Это означает, что форма операции пытается создать постоянную каталожную ТМЦ напрямую, а не временную.

Для сценария временных ТМЦ это неправильная точка интеграции, потому что:

- обходится серверный процесс модерации;
- пользователь уровня `storekeeper` получает UX, который не совпадает с новой моделью;
- логика формы операции начинает конкурировать с отдельным каталогом.

### 3. Отрисовка операций завязана на lookup по `item_id`

Сейчас `OperationPageService._present_operation()` в `apps/operations/services.py` берёт имя, SKU и единицу измерения из локального индекса каталога по `item_id`.

Для временных ТМЦ этого недостаточно:

- у строки может не быть обычного `item_id` как главного источника отображения;
- после approve/merge UI должен показывать историческое snapshot-имя, а не подменять его текущим каталогом;
- UI должен отдельно уметь показывать, во что была разрешена временная ТМЦ.

### 4. Экранов модерации временных ТМЦ в Django нет

В клиенте нет:

- API-обёртки для `/temporary-items`;
- раздела списка временных ТМЦ;
- карточки временной ТМЦ;
- действий approve/merge;
- экрана истории операций по временной ТМЦ.

### 5. Остатки тоже жёстко привязаны к каталожному `item_id`

`apps/balances/views.py` сейчас строит отображение через `_get_items_index()` и `_present_balance_row()`, то есть опять через lookup постоянного каталога.

Если сервер уже возвращает строки, в которых важны `display_name`, `resolved_item_id` или другие поля read-model временных ТМЦ, клиенту потребуется отдельная адаптация и здесь.

---

## Ключевая рекомендация

### Основное решение

Рекомендуется внедрять временные ТМЦ в `Warehouse_web` как отдельный клиентский сценарий, а не как небольшой патч в текущем inline create.

Предпочтительная структура:

1. Новый `apps/sync_client/temporary_items_api.py`
2. Новый Django app `apps/temporary_items`
3. Переработка `apps/operations` для отправки временных ТМЦ в payload операции
4. Доработка `OperationPageService` и экранов операций для корректного исторического отображения
5. Второй очередью — доработка экранов остатков и отчётных read-model, если они выводят временные позиции

### Почему отдельный app лучше, чем прятать всё внутрь `apps/catalog`

Причины:

- временные ТМЦ не являются частью обычного каталога до момента решения модератора;
- у них отдельный жизненный цикл и отдельные действия;
- у них есть собственная история операций;
- модерация временных ТМЦ логически находится между `operations` и `catalog`, а не внутри чистого каталога.

Рекомендация по UX:

- в sidebar добавить новый подпункт для пользователей с `can_manage_catalog`;
- логичное место: рядом с блоком `Номенклатура`, например пункт `Временные ТМЦ`.

---

## Рекомендуемая архитектура клиента

### 1. Новый SyncServer API-клиент

Создать `apps/sync_client/temporary_items_api.py` по аналогии с `catalog_api.py` и `operations_api.py`.

Минимальный состав методов:

- `list_temporary_items(filters=None, *, acting_user_id=None, acting_site_id=None)`
- `get_temporary_item(temporary_item_id, *, acting_user_id=None, acting_site_id=None)`
- `list_temporary_item_operations(temporary_item_id, filters=None, *, acting_user_id=None, acting_site_id=None)`
- `approve_as_item(temporary_item_id, *, acting_user_id=None, acting_site_id=None)`
- `merge_to_item(temporary_item_id, payload, *, acting_user_id=None, acting_site_id=None)`

Ожидаемые правила:

- весь HTTP доступ только через `SyncServerClient`;
- никаких прямых Django ORM-моделей для временных ТМЦ не добавлять;
- ошибки не гасить, а приводить к существующим `SyncServerAPIError`-классам.

### 2. Новый Django app `apps/temporary_items`

Рекомендуемый минимум:

- `apps/temporary_items/apps.py`
- `apps/temporary_items/urls.py`
- `apps/temporary_items/views.py`
- `apps/temporary_items/services.py`
- `apps/temporary_items/tests.py`
- `templates/temporary_items/list.html`
- `templates/temporary_items/detail.html`

Основные маршруты:

- `GET /temporary-items/` — список
- `GET /temporary-items/<id>/` — карточка
- `POST /temporary-items/<id>/approve/` — approve-as-item
- `POST /temporary-items/<id>/merge/` — merge

В `config/urls.py` добавить отдельный include.

### 3. Переработка формы создания операции

Точка врезки:

- `apps/operations/views.py`
- `apps/operations/forms.py`
- `templates/operations/form.html`
- клиентский JS, который обслуживает hidden `draft_payload`

Что нужно изменить:

- разрешить строке черновика быть либо каталожной, либо временной;
- хранить в черновике признак типа строки, например `kind: "catalog" | "temporary"`;
- при наличии хотя бы одной временной строки обязательно добавлять `client_request_id`;
- `client_request_id` должен жить вместе с черновиком и переиспользоваться при повторной отправке того же draft-а;
- для каждой временной строки генерировать `client_key`;
- для временной строки собирать объект `temporary_item`, а не `item_id`.

Рекомендуемый внутренний формат draft в браузере:

```json
{
  "operation_type": "RECEIVE",
  "site_id": 1,
  "effective_at": "2026-04-23T16:00",
  "client_request_id": "7e31b0ee-f7b3-4fb6-b7a8-4d31ab6d89fb",
  "items": [
    {
      "kind": "catalog",
      "item_id": 101,
      "name": "Кабель ВВГнг 3х2.5",
      "sku": "VVG-325",
      "unit_symbol": "м",
      "quantity": "5"
    },
    {
      "kind": "temporary",
      "client_key": "tmp-2",
      "name": "Кабель без карточки",
      "sku": "",
      "unit_id": 3,
      "unit_symbol": "м",
      "category_id": 7,
      "category_name": "Кабели",
      "description": "",
      "quantity": "2"
    }
  ]
}
```

Критически важное правило для UI:

- временные строки нельзя автоматически склеивать только по имени;
- существующие каталожные строки можно объединять по `item_id`, как сейчас;
- временная строка должна жить как самостоятельная сущность draft-а.

### 4. Убрать из формы операции текущий сценарий «создать постоянную ТМЦ»

Текущий inline create в `templates/operations/form.html` и `OperationItemCreateView` рекомендуется заменить.

Предпочтительный вариант:

- в форме операции оставить поиск по существующему каталогу;
- рядом добавить отдельный блок `Добавить временную ТМЦ`;
- создание постоянной ТМЦ оставить только в разделе номенклатуры.

Если нужен компромиссный вариант:

- для `chief_storekeeper` можно оставить две явные кнопки:
  - `Добавить временную ТМЦ`
  - `Открыть создание постоянной ТМЦ в каталоге`

Но даже в этом варианте не стоит создавать постоянную ТМЦ прямо из AJAX-обработчика формы операции.

### 5. Исправить представление операций

Точка врезки:

- `apps/operations/services.py`
- `templates/operations/detail.html`
- `templates/operations/list.html`

`OperationPageService._present_operation()` должен перейти с модели "всё берём из каталога по item_id" на более устойчивую схему:

1. Основное имя строки:
   - сначала `item_name_snapshot`
   - если его нет, тогда имя из каталога
2. SKU:
   - сначала `item_sku_snapshot`
   - потом каталог
3. Единица измерения:
   - сначала `unit_symbol_snapshot`
   - потом каталог
4. Если есть `temporary_item_id`, показывать badge `Временная ТМЦ`
5. Если есть `resolved_item_id`, показывать вторичную подпись:
   - `Разрешена в ТМЦ <resolved_item_name>`

Это обязательно, иначе после merge/approve история на клиенте будет выглядеть неисторично.

### 6. Экран списка временных ТМЦ

MVP-функции списка:

- фильтр по статусу;
- поиск по имени/SKU;
- фильтр по `resolved_item_id`;
- пагинация;
- колонка `Статус`;
- колонка `Создана`;
- колонка `Создал`;
- колонка `Связана с ТМЦ`;
- ссылка в карточку.

Рекомендуемые статусы для UX:

- `active` — ждёт разбора
- `approved_as_item` — утверждена как новая ТМЦ
- `merged_to_item` — слита с существующей ТМЦ

### 7. Карточка временной ТМЦ

Карточка должна показывать:

- все поля `TemporaryItemResponse`;
- техническую связь с backing item без акцента на внутреннюю модель;
- текущий статус;
- `resolved_item_id` и тип решения;
- историю операций через `GET /temporary-items/{id}/operations`.

Действия на карточке:

- `Approve as item`
- `Merge to existing item`

Для merge нужен выбор целевой постоянной ТМЦ. Рекомендуемый источник выбора:

- существующий `CatalogService.browse_items()`
- только активные каталожные ТМЦ
- без показа временных ТМЦ в этом поиске

### 8. DTO-адаптация для остатков и других read-model

Это можно делать второй очередью, но учитывать сразу в дизайне.

Нужно быть готовыми, что balances/read-model на сервере будут возвращать поля не только через `item_id`, но и через:

- `display_name`
- `resolved_item_id`
- `resolved_item_name`
- данные временной сущности

Рекомендация:

- в `apps/balances/views.py` не полагаться только на индекс каталога;
- добавить адаптер отображения, который умеет предпочитать серверное display-имя;
- если строка связана с временной ТМЦ, UI должен не терять её из-за отсутствия стандартной каталожной карточки.

---

## Поэтапный план внедрения

### Этап 1. Транспорт и контракты

- добавить `apps/sync_client/temporary_items_api.py`;
- покрыть его unit-тестами;
- описать endpoint mapping в документации `Warehouse_web/docs`.

### Этап 2. Создание операций с временными ТМЦ

- переделать draft model в `templates/operations/form.html`;
- переделать `_build_create_payload()` в `apps/operations/views.py`;
- добавить генерацию и сохранение `client_request_id`;
- заменить inline create постоянной ТМЦ на ввод временной строки.

Результат этапа:

- storekeeper/chief могут создать операцию с временной ТМЦ;
- сервер создаёт temporary item через payload операции;
- повторный submit не создаёт дублей при корректном reuse `client_request_id`.

### Этап 3. Корректное чтение истории операций

- обновить `OperationPageService._present_operation()`;
- обновить `templates/operations/detail.html`;
- при необходимости обновить `templates/operations/list.html`.

Результат этапа:

- в карточке операции корректно показываются временные строки;
- после approve/merge сохраняется историческое имя строки;
- UI дополнительно показывает resolved target.

### Этап 4. Раздел модерации временных ТМЦ

- добавить `apps/temporary_items`;
- добавить sidebar entry;
- сделать список и карточку;
- подключить approve и merge.

Результат этапа:

- `chief_storekeeper` и `root` могут разбирать временные ТМЦ из Django-клиента без обращения к сырому API.

### Этап 5. Остатки и полировка

- проверить `balances`-экраны;
- при необходимости обновить отображение item label;
- добавить ссылочную навигацию между операцией, временной ТМЦ и resolved item.

---

## Что не рекомендуется делать

- не создавать локальную Django-модель `TemporaryItem` как источник истины;
- не складывать временные ТМЦ в локальный `catalog_cache` как обычные каталожные ТМЦ;
- не подменять историческое имя строки операции текущим именем resolved item;
- не оставлять старый AJAX endpoint, который создаёт постоянную ТМЦ прямо из формы операции;
- не смешивать moderation UI с обычным списком каталога.

---

## Минимальные изменения по файлам

### Обязательно изменить

- `apps/operations/views.py`
- `apps/operations/forms.py`
- `apps/operations/services.py`
- `apps/operations/tests.py`
- `templates/operations/form.html`
- `templates/operations/detail.html`
- `templates/includes/sidebar.html`
- `config/urls.py`

### Добавить

- `apps/sync_client/temporary_items_api.py`
- `apps/temporary_items/*`
- `templates/temporary_items/*`

### Вероятно изменить второй очередью

- `apps/balances/views.py`
- `templates/balances/list.html`

---

## Тесты, которые обязательно нужны

### Unit / service tests

- `_build_create_payload()` умеет смешанные строки: `item_id` + `temporary_item`
- `client_request_id` добавляется и сохраняется при временных строках
- одинаковые временные строки не склеиваются по имени
- `OperationPageService._present_operation()` корректно предпочитает snapshot-поля

### View tests

- create operation view отправляет payload с `temporary_item`
- список временных ТМЦ доступен только `chief_storekeeper/root`
- approve action корректно вызывает backend endpoint
- merge action корректно вызывает backend endpoint и передаёт `target_item_id`

### Интеграционные проверки на стенде

- операция с временной ТМЦ создаётся из Django UI;
- карточка операции показывает snapshot-имя;
- после approve в карточке операции видно `resolved_item_name`;
- после merge временная ТМЦ исчезает из активного списка и появляется связь с целевой постоянной ТМЦ.

---

## Рекомендуемый MVP

Если нужен минимальный, но рабочий релиз, то рекомендую такой состав:

1. Переработать создание операции под `temporary_item`
2. Добавить `TemporaryItemsAPI`
3. Сделать список и карточку временных ТМЦ
4. Добавить approve/merge
5. Исправить detail view операции под snapshot/resolved fields

Этого уже достаточно, чтобы сценарий:

- создать временную ТМЦ при оформлении операции;
- увидеть её в очереди модерации;
- разрешить как новую постоянную или слить с существующей;
- не потерять историческую корректность операции.

---

## Вывод

Для `Warehouse_web` это не просто добавление нового endpoint-а. Это небольшая, но отдельная клиентская подсистема:

- ввод временной ТМЦ в операции;
- модерация временной ТМЦ;
- корректное историческое отображение после resolution.

Самая важная доработка — перестать создавать постоянную ТМЦ из формы операции и перевести этот поток на серверный механизм `temporary_item`.
