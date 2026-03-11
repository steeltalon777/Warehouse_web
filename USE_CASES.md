# USE_CASES

## 1) Просмотр категорий
1. Пользователь открывает `/catalog/categories/`.
2. View вызывает `CatalogService.list_categories()`.
3. Service обращается в SyncServer `GET /catalog/categories`.
4. UI рендерит список или ошибку.

## 2) Создание категории
1. Пользователь открывает форму `/catalog/categories/create/`.
2. Отправляет `name`, `code`, `parent_id`, `sort_order`, `is_active`.
3. View валидирует форму и вызывает `CatalogService.create_category()`.
4. Service отправляет `POST /catalog/admin/categories`.
5. При успехе — redirect на список, иначе ошибка формы.

## 3) Обновление/деактивация категории
1. Пользователь открывает `/catalog/categories/<id>/edit/` или deactivate route.
2. Для edit отправляется `PATCH /catalog/admin/categories/{id}`.
3. Для deactivate отправляется `PATCH ...` с `is_active=false`.
4. UI показывает success/error.

## 4) Управление единицами измерения
1. Пользователь работает с `/catalog/units/` и `/catalog/units/create/`.
2. Read через `GET /catalog/units`, write через `POST/PATCH /catalog/admin/units...`.
3. Ошибки отображаются через `form_error`.

## 5) Управление номенклатурой (Item)
1. Пользователь открывает `/catalog/items/` (опционально `category_id` и `search`).
2. View запрашивает items + categories для фильтров.
3. Создание/изменение через `POST/PATCH /catalog/admin/items...`.
4. Деактивация через `PATCH` с `is_active=false`.

## 6) Доступ в клиентский раздел
1. Пользователь открывает `/client/`.
2. Проверяется `can_use_client(user)`.
3. При доступе рендерится dashboard, иначе `403`.

## 7) Аутентификация
1. Вход через `/users/login/` (Django LoginView).
2. Выход через `/users/logout/`.
3. После входа redirect на `/client/`.
