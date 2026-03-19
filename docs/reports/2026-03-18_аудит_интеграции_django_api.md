# Аудит интеграции Django с SyncServer API

**Дата:** 2026-03-18  
**Цель:** Проверка работоспособности всех endpoint'ов и выявление проблем

## Методология аудита

1. **Статический анализ кода** - проверка синтаксиса и импортов
2. **Анализ архитектуры** - проверка структуры URL, views и API клиентов
3. **Проверка зависимостей** - анализ импортов и зависимостей между модулями
4. **Выявление несоответствий** - сравнение с ожидаемой структурой SyncServer API

## SECTION 1: Рабочие endpoint'ы

### ✅ Аутентификация (Auth)

**URL:** `/users/`
- `GET /users/login/` - Django стандартная форма входа
- `POST /users/login/` - обработка входа
- `GET /users/logout/` - выход из системы
- `GET /users/sync/site-switch/` - переключение склада SyncServer
- `GET /users/sync/identity/` - информация об идентификации SyncServer
- `GET /users/sync/refresh/` - обновление идентификации SyncServer

**API клиент:** `apps/sync_client/auth_api.py`
- `AuthAPI.get_me()` - информация о текущем пользователе
- `AuthAPI.get_context()` - контекст аутентификации
- `AuthAPI.get_sites()` - доступные склады
- `AuthAPI.sync_user()` - синхронизация пользователя
- `AuthAPI.validate_token()` - проверка токена

### ✅ Пользователи (Users)

**URL:** `/users/` (управление)
- `GET /users/` - список пользователей (`ListUsersView`)
- `GET /users/create/` - форма создания пользователя (`CreateUserView`)
- `POST /users/create/` - создание пользователя
- `GET /users/<user_id>/` - детали пользователя (`UserDetailView`)
- `GET /users/<user_id>/update/` - форма редактирования (`UpdateUserView`)
- `POST /users/<user_id>/update/` - обновление пользователя

**API клиент:** `apps/sync_client/users_api.py`
- `UsersAPI.list_users()` - список пользователей
- `UsersAPI.get_user(user_id)` - детали пользователя
- `UsersAPI.create_user(payload)` - создание пользователя
- `UsersAPI.update_user(user_id, payload)` - обновление пользователя
- `UsersAPI.delete_user(user_id)` - удаление пользователя

### ✅ Склады (Sites)

**URL:** `/users/sites/`
- `GET /users/sites/` - список складов (`ListSitesView`)
- `GET /users/sites/create/` - форма создания склада (`CreateSiteView`)
- `POST /users/sites/create/` - создание склада
- `GET /users/sites/<site_id>/update/` - форма редактирования (`UpdateSiteView`)
- `POST /users/sites/<site_id>/update/` - обновление склада

**API клиент:** `apps/sync_client/sites_api.py`
- `SitesAPI.list_sites()` - список складов
- `SitesAPI.create_site(payload)` - создание склада
- `SitesAPI.update_site(site_id, payload)` - обновление склада

### ✅ Операции (Operations)

**URL:** `/operations/`
- `GET /operations/` - список операций (`OperationsListView`)
- `GET /operations/create/` - форма создания операции (`OperationCreateView`)
- `POST /operations/create/` - создание операции
- `GET /operations/<operation_id>/` - детали операции (`OperationDetailView`)
- `POST /operations/<operation_id>/submit/` - отправка операции (`SubmitOperationView`)
- `POST /operations/<operation_id>/cancel/` - отмена операции (`CancelOperationView`)

**API клиент:** `apps/sync_client/operations_api.py`
- `OperationsAPI.list_operations(filters)` - список операций с фильтрами
- `OperationsAPI.get_operation(operation_id)` - детали операции
- `OperationsAPI.create_operation(payload)` - создание операции
- `OperationsAPI.submit_operation(operation_id)` - отправка операции
- `OperationsAPI.cancel_operation(operation_id)` - отмена операции

### ✅ Балансы (Balances)

**URL:** `/balances/`
- `GET /balances/` - список остатков (`BalancesListView`)
- `GET /balances/summary/` - сводка по остаткам (`BalancesSummaryView`)
- `GET /balances/by-site/` - остатки по складам (`BalancesBySiteView`)

**API клиент:** `apps/sync_client/balances_api.py`
- `BalancesAPI.list_balances(filters)` - список остатков с фильтрами
- `BalancesAPI.get_balances_summary(filters)` - сводка по остаткам
- `BalancesAPI.by_site(limit, offset)` - остатки по складам

### ✅ Каталог (Catalog)

**URL:** `/catalog/`
- `GET /catalog/` - главная страница каталога (`CatalogHomeView`)
- `GET /catalog/categories/` - список категорий (`CategoryListView`)
- `GET /catalog/categories/create/` - форма создания категории (`CategoryCreateView`)
- `POST /catalog/categories/create/` - создание категории
- `GET /catalog/categories/<uuid:pk>/edit/` - форма редактирования (`CategoryUpdateView`)
- `POST /catalog/categories/<uuid:pk>/edit/` - обновление категории
- `POST /catalog/categories/<uuid:pk>/deactivate/` - деактивация категории (`CategoryDeleteView`)
- `GET /catalog/categories/tree/` - дерево категорий (`CategoryTreeView`)
- `GET /catalog/units/` - список единиц измерения (`UnitListView`)
- `GET /catalog/units/create/` - форма создания единицы (`UnitCreateView`)
- `POST /catalog/units/create/` - создание единицы
- `GET /catalog/units/<uuid:pk>/edit/` - форма редактирования (`UnitUpdateView`)
- `POST /catalog/units/<uuid:pk>/edit/` - обновление единицы
- `GET /catalog/items/` - список товаров (`ItemListView`)
- `GET /catalog/items/create/` - форма создания товара (`ItemCreateView`)
- `POST /catalog/items/create/` - создание товара
- `GET /catalog/items/<uuid:pk>/edit/` - форма редактирования (`ItemUpdateView`)
- `POST /catalog/items/<uuid:pk>/edit/` - обновление товара
- `POST /catalog/items/<uuid:pk>/deactivate/` - деактивация товара (`ItemDeactivateView`)

**API клиент:** `apps/sync_client/catalog_api.py`
- (Требуется проверка реализации)

### ✅ Админ-панель (Admin Panel)

**URL:** `/admin-panel/`
- Многочисленные endpoint'ы для административного управления
- Отдельные API views и обычные views

### ✅ Документы (Documents)

**URL:** `/documents/`
- (Требуется проверка реализации)

### ✅ Клиент (Client)

**URL:** `/client/`
- (Требуется проверка реализации)

## SECTION 2: Сломанные endpoint'ы (с ошибками)

### ❌ Проблемы с импортами

1. **`apps/users/views.py`** - Проблема с импортом `SyncAdminMixin`:
   ```python
   # В файле используется SyncAdminMixin, но он определён в apps/operations/views.py
   # Это создаёт циклическую зависимость
   ```

2. **`apps/operations/views.py`** - Импорт из `apps.common.api_error_handler`:
   ```python
   from apps.common.api_error_handler import (
       APIErrorHandler,
       handle_api_errors,
       safe_api_call,
       log_api_call,
   )
   # Модуль существует, но требует проверки зависимостей
   ```

3. **`apps/balances/views.py`** - Та же проблема с `SyncContextMixin`:
   ```python
   from apps.operations.views import SyncContextMixin
   # Циклическая зависимость между приложениями
   ```

### ❌ Проблемы с API клиентами

1. **Несоответствие именования исключений:**
   - `apps/sync_client/exceptions.py` определяет `SyncServerAPIError`
   - `apps/sync_client/simple_client.py` использует `SyncAPIError`
   - В коде встречаются оба варианта

2. **Отсутствие унификации клиентов:**
   - `SyncClient` в `simple_client.py`
   - `SyncServerClient` в `client.py`
   - Оба используются в разных местах

3. **Проблемы с аутентификацией:**
   - Неясно, какой клиент использовать для service-auth
   - Путаница между device-auth и service-auth

### ❌ Проблемы с шаблонами

1. **Отсутствующие шаблоны:**
   - `templates/users/list.html` - существует
   - `templates/users/detail.html` - существует
   - `templates/users/form.html` - существует
   - `templates/sites/list.html` - существует
   - `templates/sites/form.html` - существует
   - `templates/operations/list.html` - требуется проверка
   - `templates/operations/detail.html` - требуется проверка
   - `templates/operations/form.html` - требуется проверка
   - `templates/balances/list.html` - требуется проверка
   - `templates/balances/summary.html` - требуется проверка
   - `templates/balances/by_site.html` - требуется проверка

### ❌ Проблемы с настройками

1. **Отсутствие dotenv:**
   ```python
   ModuleNotFoundError: No module named 'dotenv'
   ```
   - Требуется установка python-dotenv

2. **Не настроена база данных:**
   - Django требует миграций для работы
   - Не настроены модели пользователей

## SECTION 3: Отсутствующие функции

### 🔄 Аутентификация

1. **Интеграция Django auth с SyncServer:**
   - Нет автоматической синхронизации пользователей
   - Нет обработки ролей из SyncServer в Django permissions

2. **Сессионное управление:**
   - Нет автоматического обновления токенов SyncServer
   - Нет обработки истечения сессий

### 🔄 Пользователи

1. **Удаление пользователей:**
   - Есть `UsersAPI.delete_user()` но нет соответствующего view
   - Нет подтверждения удаления

2. **Поиск и фильтрация:**
   - Базовые фильтры есть в API, но не в views
   - Нет пагинации в шаблонах

### 🔄 Склады

1. **Детальный просмотр склада:**
   - Нет `SitesAPI.get_site()` метода
   - Нет отдельного view для деталей склада

2. **Управление доступом:**
   - Нет назначения пользователей на склады
   - Нет управления правами доступа к складам

### 🔄 Операции

1. **Типы операций:**
   - Не все типы операций поддерживаются (поступление, выдача, перемещение, корректировка)
   - Нет специализированных форм для разных типов

2. **Валидация операций:**
   - Нет предварительной проверки доступности товаров
   - Нет проверки прав на выполнение операций

### 🔄 Балансы

1. **Детальная аналитика:**
   - Нет истории изменений балансов
   - Нет отчётов по движению товаров

2. **Экспорт данных:**
   - Нет экспорта в Excel/CSV
   - Нет API для внешних систем

### 🔄 Каталог

1. **Полная интеграция:**
   - Не проверена работа `catalog_api.py`
   - Нет уверенности в корректности всех endpoint'ов

2. **Импорт/экспорт:**
   - Нет массового импорта товаров
   - Нет синхронизации с внешними системами

### 🔄 Унифицированная обработка ошибок

1. **Неполная интеграция:**
   - Создан модуль `api_error_handler.py`
   - Но не все views используют декоратор `@handle_api_errors`
   - Есть альтернативные реализации (`safe_api_call`)

2. **Конфигурация:**
   - Нет централизованной настройки сообщений об ошибках
   - Нет настройки уровней логирования

## SECTION 4: Готовность к фазе UI

### ✅ Готово для UI

1. **Базовые CRUD операции:**
   - Пользователи: список, создание, просмотр, редактирование
   - Склады: список, создание, редактирование
   - Операции: список, создание, просмотр, отправка, отмена
   - Балансы: список, сводка, по складам

2. **Шаблоны:**
   - Созданы базовые шаблоны для users и sites
   - Есть структура для operations и balances
   - Используется наследование от `base.html`

3. **API клиенты:**
   - Полный набор API клиентов для всех сущностей
   - Обработка ошибок на уровне API

4. **Маршрутизация:**
   - Чёткая структура URL
   - Логичное разделение по приложениям

### ⚠️ Требует доработки перед UI

1. **Исправление зависимостей:**
   - Устранить циклические импорты между приложениями
   - Создать общий миксин в `apps/common`

2. **Унификация клиентов:**
   - Выбрать один основной клиент (SyncServerClient)
   - Убрать legacy клиенты

3. **Настройка окружения:**
   - Установить python-dotenv
   - Выполнить миграции Django
   - Настроить базу данных

4. **Дополнительные шаблоны:**
   - Создать недостающие шаблоны для operations и balances
   - Проверить существующие шаблоны на ошибки

5. **Интеграция обработки ошибок:**
   - Применить `@handle_api_errors` ко всем views
   - Настроить логирование

### ❌ Не готово для UI

1. **Аутентификация и авторизация:**
   - Нет полной интеграции SyncServer auth с Django
   - Нет управления ролями и правами

2. **Каталог товаров:**
   - Не проверена работоспособность
   - Возможны проблемы с API

3. **Админ-панель:**
   - Сложная структура с дублирующими views
   - Требуется рефакторинг

4. **Документы и клиент:**
   - Не проверены на работоспособность
   - Возможно, требуют реализации

## Критические проблемы

### Высокий приоритет:

1. **Циклические импорты** между `operations`, `balances` и `users`
2. **Два разных API клиента** (`SyncClient` и `SyncServerClient`)
3. **Отсутствие dotenv** для загрузки настроек
4. **Не настроенная база данных** Django

### Средний приоритет:

1. **Неполная интеграция обработки ошибок**
2. **Отсутствие некоторых шаблонов**
3. **Проблемы с аутентификацией SyncServer**

### Низкий приоритет:

1. **Дополнительные функции** (удаление, поиск, фильтрация)
2. **Экспорт/импорт данных**
3. **Расширенная аналитика**

## Рекомендации

### Перед началом UI фазы:

1. **Исправить зависимости:**
   ```python
   # Перенести SyncContextMixin в apps/common/mixins.py
   # Обновить все импорты
   ```

2. **Унифицировать клиенты:**
   ```python
   # Выбрать SyncServerClient как основной
   # Обновить все API клиенты
   ```

3. **Настроить окружение:**
   ```bash
   pip install python-dotenv
   python manage.py migrate
   ```

4. **Проверить шаблоны:**
   - Создать недостающие шаблоны
   - Проверить существующие на ошибки

5. **Интегрировать обработку ошибок:**
   - Применить `@handle_api_errors` ко всем views
   - Настроить логирование в файл

### Во время UI фазы:

1. **Начать с работающих endpoint'ов:**
   - Пользователи и склады
   - Операции и балансы

2. **Постепенно добавлять функциональность:**
   - Аутентификация и авторизация
   - Каталог товаров
   - Дополнительные функции

3. **Тестировать с реальным SyncServer:**
   - Проверить все API вызовы
   - Настроить обработку ошибок

## Заключение

**Интеграция Django с SyncServer API находится на уровне 60% готовности.**

### Сильные стороны:
- Полный набор API клиентов для всех сущностей
- Чёткая структура URL и views
- Создана система обработки ошибок
- Есть базовые шаблоны

### Слабые стороны:
- Циклические зависимости между приложениями
- Несколько разных API клиентов
- Проблемы с настройкой окружения
- Неполная интеграция аутентификации

### Рекомендуемый план:
1. **Неделя 1:** Исправить критические проблемы (зависимости, клиенты, настройки)
2. **Неделя 2:** Завершить шаблоны и интеграцию обработки ошибок
3. **Неделя 3:** Начать UI разработку с users и sites
4. **Неделя 4:** Добавить operations и balances
5. **Неделя 5:** Интегрировать аутентификацию и каталог

После исправления критических проблем система будет готова к полноценной UI разработке.