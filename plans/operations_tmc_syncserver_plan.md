# План изменений по операциям и созданию ТМЦ

## Scope исследования

- Обязательный поток операций: [`apps/operations/views.py`](../apps/operations/views.py), [`templates/operations/form.html`](../templates/operations/form.html), [`templates/operations/detail.html`](../templates/operations/detail.html), [`static/js/operations_create.js`](../static/js/operations_create.js)
- Каталог и создание ТМЦ: [`apps/catalog/views.py`](../apps/catalog/views.py), [`apps/catalog/forms.py`](../apps/catalog/forms.py), [`apps/catalog/services.py`](../apps/catalog/services.py), [`apps/sync_client/catalog_api.py`](../apps/sync_client/catalog_api.py), [`templates/catalog/item_form.html`](../templates/catalog/item_form.html), [`apps/catalog/nomenclature_urls.py`](../apps/catalog/nomenclature_urls.py)
- Представление данных операций: [`apps/operations/services.py`](../apps/operations/services.py), [`apps/sync_client/operations_api.py`](../apps/sync_client/operations_api.py), [`API_MAP.md`](../API_MAP.md)
- Тестовое покрытие: [`apps/operations/tests.py`](../apps/operations/tests.py)

## Текущие точки интеграции с SyncServer API

### Где формируется payload операции

1. Серверный payload для создания собирается в [`_build_create_payload()`](../apps/operations/views.py#L95) в [`apps/operations/views.py`](../apps/operations/views.py)
2. Отправка выполняется через [`OperationsAPI.create_operation()`](../apps/operations/views.py#L349) из [`apps/operations/views.py`](../apps/operations/views.py)
3. HTTP-клиент для создания операции ходит в [`/operations`](../apps/sync_client/operations_api.py#L262) в [`apps/sync_client/operations_api.py`](../apps/sync_client/operations_api.py)
4. Клиентский черновик формы живёт в [`state`](../static/js/operations_create.js#L36) и сериализуется в hidden-поле через [`syncDraftPayload()`](../static/js/operations_create.js#L111) в [`static/js/operations_create.js`](../static/js/operations_create.js)

### Где создаются items

1. SSR-форма ТМЦ отправляется из [`ItemCreateView.post()`](../apps/catalog/views.py#L829) в [`apps/catalog/views.py`](../apps/catalog/views.py)
2. На сервере создание идёт через [`CatalogService.create_item()`](../apps/catalog/views.py#L833) и далее в [`CatalogAPI.create_item()`](../apps/catalog/services.py#L279)
3. HTTP-вызов уходит в [`POST /catalog/admin/items`](../apps/sync_client/catalog_api.py#L490) из [`apps/sync_client/catalog_api.py`](../apps/sync_client/catalog_api.py)
4. Маршрут отдельной страницы создания ТМЦ — [`nomenclature:item_create`](../apps/catalog/nomenclature_urls.py#L22)

## Текущее поведение по требованиям

### 1. `effective_at` на странице создания и редактирования операции

- В текущем новом потоке операций отдельного поля `effective_at` нет ни в черновике [`_default_draft()`](../apps/operations/views.py#L70), ни в шаблоне [`templates/operations/form.html`](../templates/operations/form.html), ни в JS [`static/js/operations_create.js`](../static/js/operations_create.js)
- Payload создания операции в [`_build_create_payload()`](../apps/operations/views.py#L95) не включает `effective_at`
- Детальная страница операции [`templates/operations/detail.html`](../templates/operations/detail.html) показывает `created_at` и `updated_at`, но не показывает `effective_at`
- В текущем обязательном scope нет страницы редактирования операции: в [`apps/operations/urls.py`](../apps/operations/urls.py#L15) есть только список, создание, поиск ТМЦ, detail, submit и cancel
- При этом API действительно поддерживает `effective_at`, что видно в [`API_MAP.md`](../API_MAP.md#L5009) и отдельный PATCH для поля тоже задокументирован в [`API_MAP.md`](../API_MAP.md#L5518)
- Итог: требование сейчас не реализовано, а часть про редактирование упирается в отсутствие самого UI/route для edit в новом потоке

### 2. Быстрое создание ТМЦ со страницы операции, не покидая контекст

- На странице создания операции доступен только поиск существующей ТМЦ через [`OperationItemSearchView`](../apps/operations/views.py#L285) и [`item_search_url`](../apps/operations/views.py#L399)
- В [`templates/operations/form.html`](../templates/operations/form.html#L113) есть блок Добавить ТМЦ, но он работает только с поиском и добавлением найденных позиций
- В [`static/js/operations_create.js`](../static/js/operations_create.js#L331) поиск реализован через `fetch` к [`operations:item_search`](../apps/operations/urls.py#L17); логики создания новой ТМЦ нет
- На странице detail [`templates/operations/detail.html`](../templates/operations/detail.html) действий по созданию ТМЦ тоже нет
- Отдельная форма создания ТМЦ существует только как самостоятельная страница [`templates/catalog/item_form.html`](../templates/catalog/item_form.html) по маршруту [`nomenclature:item_create`](../apps/catalog/nomenclature_urls.py#L22)
- Итог: требование сейчас не реализовано

### 3. Во всех местах создания ТМЦ единица измерения по умолчанию — `шт`

- В форме [`ItemForm`](../apps/catalog/forms.py#L37) поле [`unit_id`](../apps/catalog/forms.py#L41) обязательно, но initial/default не задаётся
- В [`ItemCreateView.get()`](../apps/catalog/views.py#L804) initial формируется только для [`category_id`](../apps/catalog/views.py#L812), unit по умолчанию не выбирается
- В шаблоне [`templates/catalog/item_form.html`](../templates/catalog/item_form.html#L16) форма просто рендерится через `{{ form.as_p }}`, без доп. логики выбора `шт`
- Список единиц нормализуется в [`_normalize_units()`](../apps/catalog/views.py#L154), там есть доступ к `symbol`, чего достаточно для поиска единицы `шт`
- Константа по умолчанию для единицы измерения в клиентском коде не зашита
- Итог: требование сейчас не реализовано

### 4. Количества в операции должны нормально работать с дробными значениями

- Серверная валидация уже поддерживает дробные значения до 3 знаков после запятой через [`_to_decimal_qty()`](../apps/operations/views.py#L36)
- В payload строк операции количество сериализуется в строку [`qty`](../apps/operations/views.py#L168) через [`_serialize_decimal_qty()`](../apps/operations/views.py#L58)
- На клиенте ввод количества уже рассчитан на шаг `0.001` в [`templates/operations/form.html`](../templates/operations/form.html#L129) и в таблице строк в [`templates/operations/form.html`](../templates/operations/form.html#L175)
- В JS уже есть безопасный парсер дробных количеств [`parseQuantity()`](../static/js/operations_create.js#L44), расчёт суммы через milli-unit и поддержка отрицательных значений для корректировки
- Тесты на дробные количества уже есть в [`apps/operations/tests.py`](../apps/operations/tests.py#L16)
- Потенциальный недочёт только в отображении: в detail количество выводится как есть, через [`line.get("qty", line.get("quantity"))`](../apps/operations/services.py#L190), без дополнительного форматирования, но дробные значения не теряются
- Итог: базовая поддержка дробных количеств уже реализована; требование в основном закрыто, но его надо не сломать при изменениях вокруг формы и быстрого создания ТМЦ

## Минимально необходимый план реализации

### Шаг 1. Добавить `effective_at` в модель черновика операции и UI формы создания

Изменения:

1. Расширить черновик в [`_default_draft()`](../apps/operations/views.py#L70), добавив поле `effective_at`
2. На `GET`-ветке [`OperationCreateView.get()`](../apps/operations/views.py#L316) задавать дефолтное значение текущей даты/времени в формате, пригодном для `datetime-local`
3. Добавить поле ввода даты/времени в [`templates/operations/form.html`](../templates/operations/form.html#L46) в секцию параметров документа
4. Расширить клиентское состояние в [`ensureStateDefaults()`](../static/js/operations_create.js#L89), [`updateStateFromFields()`](../static/js/operations_create.js#L208), [`setFieldValuesFromState()`](../static/js/operations_create.js#L218), чтобы `effective_at` сохранялся в hidden draft
5. Добавить клиентскую проверку, что значение либо пустое, либо имеет корректный формат

Примечание:

- Сервер по API умеет подставлять текущее UTC при отсутствии значения, но по требованию UI должен показывать дефолтно текущее дата/время, поэтому лучше явно отправлять выбранное значение

### Шаг 2. Прокинуть `effective_at` в payload операции и отображение detail

Изменения:

1. Дополнить [`_build_create_payload()`](../apps/operations/views.py#L95), чтобы он:
   - читал `effective_at` из `draft_data`
   - валидировал значение
   - преобразовывал локальное значение из `datetime-local` в ISO 8601 для SyncServer
   - добавлял `effective_at` в итоговый payload только если значение прошло валидацию
2. При необходимости вынести преобразование в отдельный helper рядом с [`_to_decimal_qty()`](../apps/operations/views.py#L36)
3. В [`OperationPageService._present_operation()`](../apps/operations/services.py#L172) начать пробрасывать `effective_at` в подготовленные данные без потери значения
4. В [`templates/operations/detail.html`](../templates/operations/detail.html#L24) добавить отображение `effective_at` рядом с `created_at` и `updated_at`

Примечание:

- В текущем scope нет edit-page операции, поэтому реализация покрывает создание и отображение значения в карточке; отсутствие отдельного экрана редактирования нужно явно зафиксировать как gap текущего UI

### Шаг 3. Спроектировать быстрый сценарий создания ТМЦ внутри контекста операции

Минимально инвазивный вариант:

1. Не встраивать полноценный каталоговый flow целиком, а добавить компактную inline-форму или модальное окно на [`templates/operations/form.html`](../templates/operations/form.html)
2. Использовать существующую серверную форму [`ItemForm`](../apps/catalog/forms.py#L37) как источник полей и правил, но не вести пользователя на отдельную страницу [`nomenclature:item_create`](../apps/catalog/nomenclature_urls.py#L22)
3. Добавить новый endpoint в [`apps/operations/views.py`](../apps/operations/views.py) и [`apps/operations/urls.py`](../apps/operations/urls.py), который:
   - принимает данные новой ТМЦ из AJAX-запроса
   - использует [`CatalogService.create_item()`](../apps/catalog/services.py#L279)
   - возвращает JSON с созданной ТМЦ в формате, совместимом с поисковой выдачей [`OperationPageService._serialize_search_item()`](../apps/operations/services.py#L157)
4. В [`static/js/operations_create.js`](../static/js/operations_create.js) после успешного создания:
   - подставлять созданную ТМЦ как `selectedItem`
   - при желании сразу добавлять её в строки операции с текущим количеством
   - либо хотя бы автоматически показывать её выбранной в блоке поиска

Почему это минимальный путь:

- Повторно используется существующий сервис каталога вместо создания нового API-клиента
- Изменения локализуются в модуле операций и не ломают самостоятельную страницу каталога
- Сохраняется текущий контекст документа, как и требуется

### Шаг 4. Везде задать единицу измерения по умолчанию `шт` при создании ТМЦ

Изменения:

1. В [`apps/catalog/views.py`](../apps/catalog/views.py) после получения списка units через [`_catalog_data()`](../apps/catalog/views.py#L793) определить unit с `symbol == "шт"`
2. В [`ItemCreateView.get()`](../apps/catalog/views.py#L804) выставлять `initial["unit_id"]` на найденную единицу `шт`, если она присутствует
3. Для надёжности продублировать выбор по умолчанию в [`ItemForm.__init__()`](../apps/catalog/forms.py#L44), если:
   - форма создаётся без bound-data
   - initial для [`unit_id`](../apps/catalog/forms.py#L41) не задан
   - в `units` найден symbol `шт`
4. Ту же логику использовать для inline-формы быстрого создания ТМЦ из шага 3, чтобы поведение было единым

Примечание:

- Категория по умолчанию `__UNCATEGORIZED__` уже частично поддержана: пустой [`category_id`](../apps/catalog/forms.py#L75) уходит как `None`, а UI уже объясняет автоматическое сохранение в системную категорию. В рамках данного scope дополнительно код категории обычно не нужно явно подставлять на клиенте, если серверный create-item уже трактует пустую категорию как `Без категории`

### Шаг 5. Не ухудшить поддержку дробных количеств и добавить точечные проверки

Изменения:

1. Не менять существующую логику [`parseQuantity()`](../static/js/operations_create.js#L44), [`_to_decimal_qty()`](../apps/operations/views.py#L36) и сериализацию [`qty`](../apps/operations/views.py#L168)
2. Для быстрого создания ТМЦ убедиться, что после создания новой позиции добавление в документ использует тот же путь [`mergeItem()`](../static/js/operations_create.js#L238) и те же проверки количества
3. Расширить тесты в [`apps/operations/tests.py`](../apps/operations/tests.py) сценариями, где:
   - в payload одновременно присутствует `effective_at` и дробный `qty`
   - быстро созданная ТМЦ может быть добавлена с дробным количеством
   - дробные значения не округляются сверх 3 знаков и не теряются

## Риски и неясности

1. В новом обязательном потоке нет страницы редактирования операции
   - Требование говорит о странице создания/редактирования операции, но в [`apps/operations/urls.py`](../apps/operations/urls.py#L15) edit-route отсутствует
   - Значит, в текущем scope реально можно внедрить `effective_at` в create-flow и в detail-display, а edit-flow требует отдельной постановки или расширения scope

2. Не подтверждён формат, который ожидает SyncServer для `effective_at` при вводе из `datetime-local`
   - В документации есть ISO-строка вида `...Z` в [`API_MAP.md`](../API_MAP.md#L5009)
   - Нужно согласовать преобразование локального времени пользователя в UTC перед отправкой

3. Быстрое создание ТМЦ внутри операции сейчас не имеет готового JSON-endpoint
   - Для реализации придётся добавить новый endpoint в модуль операций или переиспользовать каталоговый view через отдельный JSON-режим
   - Первый вариант чище по UX, но потребует серверной прослойки

4. Для unit по умолчанию `шт` клиент зависит от наличия такой единицы в доступном списке
   - Если в окружении единица не заведена или символ отличается, default не сработает
   - Нужен fallback: оставить поле обязательным и не подставлять значение, если `шт` не найден

5. Поведение категории по умолчанию `__UNCATEGORIZED__` в клиенте опирается на серверную трактовку пустого `category_id`
   - В UI это уже подразумевается в [`ItemForm`](../apps/catalog/forms.py#L56) и [`templates/catalog/item_form.html`](../templates/catalog/item_form.html#L14)
   - Но если SyncServer когда-то потребует явный numeric `category_id`, потребуется отдельный lookup системной категории по коду `__UNCATEGORIZED__`

## Рекомендуемый порядок внедрения

1. Добавить `effective_at` в create-flow операции и detail-view
2. Закрыть тестами совместимость `effective_at` с дробными `qty`
3. Внедрить единицу измерения по умолчанию `шт` в общий flow создания ТМЦ
4. Затем добавить inline-механику быстрого создания ТМЦ на странице операции, уже опираясь на единое поведение формы item
5. После этого отдельно решить, нужен ли полноценный edit-flow операции в новом UI, если требование про редактирование остаётся обязательным

## Краткий todo-list для реализации в следующем режиме

- [ ] Добавить `effective_at` в draft state, HTML-форму и сериализацию операции
- [ ] Валидировать и преобразовывать `effective_at` в payload [`POST /operations`](../apps/sync_client/operations_api.py#L262)
- [ ] Отображать `effective_at` в карточке операции
- [ ] Выставлять `unit_id` по умолчанию на единицу с symbol `шт` во всех create-flow ТМЦ
- [ ] Добавить AJAX-endpoint быстрого создания ТМЦ в модуле операций
- [ ] Добавить UI быстрого создания ТМЦ на странице операции и автоподстановку созданной позиции
- [ ] Расширить тесты на `effective_at`, default unit и сохранение поддержки дробных `qty`
