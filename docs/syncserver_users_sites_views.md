# Django Views для управления пользователями и складами через SyncServer API

## Обзор

Этот модуль предоставляет Django представления для управления пользователями и складами через SyncServer API. Все операции выполняются через API клиенты, без использования Django ORM.

## Реализованные представления

### Пользователи (Users)

1. **`ListUsersView`** - Список пользователей
   - **URL:** `/users/`
   - **Метод:** GET
   - **API:** `UsersAPI.list_users()`
   - **Шаблон:** `users/list.html`

2. **`UserDetailView`** - Детали пользователя
   - **URL:** `/users/<user_id>/`
   - **Метод:** GET
   - **API:** `UsersAPI.get_user(user_id)`
   - **Шаблон:** `users/detail.html`

3. **`CreateUserView`** - Создание пользователя
   - **URL:** `/users/create/`
   - **Методы:** GET (форма), POST (создание)
   - **API:** `UsersAPI.create_user(payload)`
   - **Шаблон:** `users/form.html`

4. **`UpdateUserView`** - Обновление пользователя
   - **URL:** `/users/<user_id>/update/`
   - **Методы:** GET (форма), POST (обновление)
   - **API:** `UsersAPI.update_user(user_id, payload)`
   - **Шаблон:** `users/form.html`

### Склады (Sites)

1. **`ListSitesView`** - Список складов
   - **URL:** `/users/sites/`
   - **Метод:** GET
   - **API:** `SitesAPI.list_sites()`
   - **Шаблон:** `sites/list.html`

2. **`CreateSiteView`** - Создание склада
   - **URL:** `/users/sites/create/`
   - **Методы:** GET (форма), POST (создание)
   - **API:** `SitesAPI.create_site(payload)`
   - **Шаблон:** `sites/form.html`

3. **`UpdateSiteView`** - Обновление склада
   - **URL:** `/users/sites/<site_id>/update/`
   - **Методы:** GET (форма), POST (обновление)
   - **API:** `SitesAPI.update_site(site_id, payload)`
   - **Шаблон:** `sites/form.html`

## Архитектура

### Базовый миксин: `SyncAdminMixin`

```python
class SyncAdminMixin(LoginRequiredMixin):
    def setup(self, request, *args, **kwargs):
        # 1. Получаем идентификацию SyncServer из сессии
        sync_identity = getattr(request, 'sync_identity', None)
        
        # 2. Инициализируем SyncServerClient с правами пользователя
        self.client = SyncServerClient(
            user_id=sync_identity.user_id if sync_identity else "admin",
            site_id=sync_identity.site_id if sync_identity else "main"
        )
        
        # 3. Инициализируем API клиенты
        self.users_api = UsersAPI(self.client)
        self.sites_api = SitesAPI(self.client)
```

### Поток данных для пользователей

```
Запрос Django → SyncAdminMixin → UsersAPI → SyncServerClient → SyncServer API
                                 ↓
Шаблон Django ← Контекст ← Ответ API ← Обработка ошибок
```

### Поток данных для складов

```
Запрос Django → SyncAdminMixin → SitesAPI → SyncServerClient → SyncServer API
                                 ↓
Шаблон Django ← Контекст ← Ответ API ← Обработка ошибок
```

## Обработка ошибок

Все представления используют единый подход к обработке ошибок:

```python
try:
    # Вызов API
    users = self.users_api.list_users()
except SyncServerAPIError as exc:
    # Ошибки API логируются и показываются пользователю
    logger.error(f"Failed to fetch users: {exc}")
    messages.error(self.request, f"Ошибка при получении списка пользователей: {exc}")
except Exception as exc:
    # Неожиданные ошибки
    logger.exception("Unexpected error fetching users")
    messages.error(self.request, f"Неожиданная ошибка: {exc}")
```

## Валидация данных

### Для создания пользователя:
- `username` - обязательно
- `password` - обязательно
- `email` - опционально
- `role` - по умолчанию "storekeeper"
- `is_root` - булево значение

### Для обновления пользователя:
- `username` - обязательно
- `password` - опционально (только если нужно изменить)
- Остальные поля как при создании

### Для создания/обновления склада:
- `name` - обязательно
- `code` - обязательно
- `description` - опционально
- `address` - опционально
- `timezone` - по умолчанию "Europe/Moscow"

## Шаблоны

### Структура шаблонов пользователей

```
templates/users/
├── list.html      # Список пользователей
├── detail.html    # Детали пользователя
└── form.html      # Форма создания/редактирования
```

### Структура шаблонов складов

```
templates/sites/
├── list.html      # Список складов
└── form.html      # Форма создания/редактирования
```

### Общие элементы шаблонов

1. **Наследование** от `base.html`
2. **Сообщения об ошибках** через `messages.error()`
3. **Валидация форм** на стороне клиента и сервера
4. **Контекстные подсказки** для полей форм
5. **Адаптивный дизайн** с использованием CSS Grid

## Безопасность

### Аутентификация
- Все представления требуют аутентификации (`LoginRequiredMixin`)
- Используется идентификация SyncServer из сессии
- При отсутствии идентификации используются дефолтные credentials

### Авторизация
- Права доступа определяются SyncServer на основе роли пользователя
- API клиенты передают контекст пользователя в заголовках
- SyncServer проверяет права доступа к операциям

### Защита данных
- Пароли передаются только при создании/изменении пользователя
- Все запросы используют HTTPS (настроено в SyncServerClient)
- Сессионные данные защищены Django

## Использование

### Доступ к представлениям

```python
# В urls.py
from django.urls import path
from .views import ListUsersView, UserDetailView, CreateUserView, UpdateUserView

urlpatterns = [
    path("", ListUsersView.as_view(), name="list"),
    path("create/", CreateUserView.as_view(), name="create"),
    path("<str:user_id>/", UserDetailView.as_view(), name="detail"),
    path("<str:user_id>/update/", UpdateUserView.as_view(), name="update"),
]
```

### Кастомизация

#### Добавление полей в форму пользователя

```python
# В CreateUserView.post()
user_data = {
    "username": request.POST.get("username", "").strip(),
    "email": request.POST.get("email", "").strip(),
    "full_name": request.POST.get("full_name", "").strip(),
    "password": request.POST.get("password", ""),
    "role": request.POST.get("role", "storekeeper"),
    "is_root": request.POST.get("is_root") == "true",
    # Добавить новое поле
    "phone": request.POST.get("phone", "").strip(),
}
```

#### Добавление валидации

```python
# В CreateUserView.post()
if not is_valid_email(user_data["email"]):
    messages.error(request, "Некорректный email адрес")
    return render(request, self.template_name, {
        "form_title": "Создание пользователя",
        "action_url": reverse_lazy("users:create"),
        "user": user_data,
        "errors": ["Некорректный email адрес"],
    })
```

## Тестирование

### Модульное тестирование

```python
from django.test import TestCase, RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from .views import ListUsersView

class UsersViewsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        
    def test_list_users_view(self):
        request = self.factory.get('/users/')
        request.user = self.create_test_user()
        
        # Mock SyncServerClient и UsersAPI
        with patch('apps.users.views.UsersAPI') as mock_users_api:
            mock_users_api.return_value.list_users.return_value = []
            
            view = ListUsersView()
            view.setup(request)
            response = view.get(request)
            
            self.assertEqual(response.status_code, 200)
            self.assertIn('users', response.context_data)
```

### Интеграционное тестирование

1. **Тестирование с реальным SyncServer**
   - Проверка успешного получения списка пользователей
   - Проверка создания и обновления пользователей
   - Проверка обработки ошибок API

2. **Тестирование шаблонов**
   - Проверка отображения данных
   - Проверка валидации форм
   - Проверка сообщений об ошибках

## Расширение

### Добавление новых представлений

1. Создать новый класс представления, наследуя от `SyncAdminMixin`
2. Реализовать методы `get()` и/или `post()`
3. Добавить обработку ошибок API
4. Создать шаблон для отображения
5. Добавить URL маршрут

### Интеграция с другими API

```python
from apps.sync_client.catalog_api import CatalogAPI

class CatalogView(SyncAdminMixin, TemplateView):
    template_name = "catalog/list.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Инициализация дополнительного API клиента
        catalog_api = CatalogAPI(self.client)
        
        try:
            items = catalog_api.list_items()
            context["items"] = items
        except SyncServerAPIError as exc:
            messages.error(self.request, f"Ошибка при получении каталога: {exc}")
        
        return context
```

## Устранение неполадок

### Проблема: "No SyncServer identity found in request"

**Причина:** Пользователь не аутентифицирован в SyncServer
**Решение:** 
1. Проверить работу сигналов аутентификации
2. Убедиться, что `sync_identity` есть в `request`

### Проблема: "Failed to fetch users: SyncServer error"

**Причина:** Ошибка подключения к SyncServer
**Решение:**
1. Проверить настройки `SYNC_SERVER_URL`
2. Проверить доступность SyncServer
3. Проверить логи SyncServer

### Проблема: Форма не отправляется

**Причина:** Ошибки валидации на стороне клиента или сервера
**Решение:**
1. Проверить обязательные поля в форме
2. Проверить JavaScript консоль на ошибки
3. Проверить логи Django на ошибки валидации

## Производительность

### Кэширование
- API ответы могут кэшироваться на уровне Django
- Использовать `@cache_page` для статических данных
- Настроить TTL в зависимости от частоты изменений

### Пагинация
- Для больших списков реализовать пагинацию
- Использовать параметры `limit` и `offset` в API запросах
- Добавить навигацию по страницам в шаблонах

### Оптимизация запросов
- Объединять связанные запросы
- Использовать `select_related` эквиваленты в API
- Минимизировать количество API вызовов на страницу