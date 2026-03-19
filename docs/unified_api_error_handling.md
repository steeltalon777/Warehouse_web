# Унифицированная обработка ошибок API

## Обзор

Этот модуль предоставляет единый подход к обработке ошибок API SyncServer во всех представлениях Django. Реализация включает:

1. Централизованную обработку исключений
2. Пользовательские сообщения об ошибках
3. Комплексное логирование
4. Безопасное поведение при сбоях
5. Опциональные повторные попытки для временных ошибок

## Компоненты

### 1. `APIErrorHandler` - Основной обработчик ошибок

```python
from apps.common.api_error_handler import APIErrorHandler

# Обработка ошибок API
APIErrorHandler.handle_api_error(
    request, 
    error, 
    operation="API операция",
    context={"additional": "data"}
)

# Обработка общих ошибок
APIErrorHandler.handle_generic_error(
    request,
    error,
    operation="операция"
)
```

### 2. Декоратор `@handle_api_errors`

```python
from apps.common.api_error_handler import handle_api_errors

@handle_api_errors(
    operation="Получение списка пользователей",
    log_context={"view": "ListUsersView"},
    retry_transient=True,
    max_retries=3
)
def my_view(request):
    # Ваша логика представления
    pass
```

### 3. Хелпер `safe_api_call`

```python
from apps.common.api_error_handler import safe_api_call

result = safe_api_call(
    api.list_users,
    request,
    operation="Получение списка пользователей",
    filters={"status": "active"}
)
```

### 4. Функция логирования `log_api_call`

```python
from apps.common.api_error_handler import log_api_call

log_api_call(
    method="GET",
    path="/admin/users",
    status_code=200,
    response_data=response,
    context={"view": "ListUsersView"}
)
```

## Типы обрабатываемых ошибок

### SyncServer API ошибки:

1. **`SyncBackendUnavailable`** - Сеть/DNS/таймаут/проблемы подключения
2. **`SyncAuthError`** - 401 Unauthorized
3. **`SyncForbiddenError`** - 403 Forbidden
4. **`SyncNotFoundError`** - 404 Ресурс не найден
5. **`SyncValidationError`** - 400/422 Ошибка валидации
6. **`SyncConflictError`** - 409 Конфликт данных
7. **`SyncServerInternalError`** - 5xx Ошибка сервера

### Общие ошибки:

- Все другие исключения Python

## Пользовательские сообщения

Каждому типу ошибки соответствует понятное сообщение для пользователя:

| Тип ошибки | Сообщение пользователю |
|------------|------------------------|
| `SyncBackendUnavailable` | "Сервер синхронизации временно недоступен. Пожалуйста, попробуйте позже." |
| `SyncAuthError` | "Ошибка аутентификации. Пожалуйста, войдите снова." |
| `SyncForbiddenError` | "У вас недостаточно прав для выполнения этой операции." |
| `SyncNotFoundError` | "Запрашиваемый ресурс не найден." |
| `SyncValidationError` | "Ошибка в данных запроса. Проверьте введённые данные." |
| `SyncConflictError` | "Конфликт данных. Возможно, ресурс был изменён другим пользователем." |
| `SyncServerInternalError` | "Внутренняя ошибка сервера. Пожалуйста, попробуйте позже." |
| Общие ошибки | "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже." |

## Логирование

### Уровни логирования:

- **ERROR**: Критические ошибки (недоступность сервера, внутренние ошибки)
- **WARNING**: Ошибки бизнес-логики (валидация, конфликты, доступ запрещён)
- **INFO**: Успешные операции
- **DEBUG**: Детальная отладка

### Данные логирования:

```python
{
    "operation": "Получение списка пользователей",
    "error_type": "SyncAuthError",
    "status_code": 401,
    "method": "GET",
    "path": "/admin/users",
    "message": "Invalid token",
    "view": "ListUsersView",
    "user_id": "user-123"
}
```

## Повторные попытки

### Для временных ошибок:

```python
@handle_api_errors(
    operation="Отправка операции",
    retry_transient=True,
    max_retries=3
)
def submit_operation(request, operation_id):
    # Автоматические повторные попытки для:
    # - SyncBackendUnavailable
    # - SyncServerInternalError
    pass
```

### Стратегия повторных попыток:

1. **Начальная задержка**: 1 секунда
2. **Увеличение задержки**: ×2 после каждой попытки
3. **Максимальное количество попыток**: 3 (настраивается)

## Безопасное поведение

### Защита от утечки информации:

1. **Нет трассировки стека** для пользователей
2. **Общие сообщения** для внутренних ошибок
3. **Логирование полных деталей** для администраторов

### Грациозная деградация:

1. **Пустые списки** вместо сбоев представлений
2. **Перенаправление на предыдущую страницу** при ошибках
3. **Сохранение введённых данных** в формах

## Использование в представлениях

### Способ 1: Декоратор (рекомендуется)

```python
from apps.common.api_error_handler import handle_api_errors

class ListUsersView(TemplateView):
    template_name = "users/list.html"
    
    @handle_api_errors(operation="Получение списка пользователей")
    def get_context_data(self, **kwargs):
        # Ваша логика
        users = self.users_api.list_users()
        return {"users": users}
```

### Способ 2: Хелпер `safe_api_call`

```python
from apps.common.api_error_handler import safe_api_call

class SimpleListView(TemplateView):
    template_name = "users/list.html"
    
    def get_context_data(self, **kwargs):
        users = safe_api_call(
            self.users_api.list_users,
            self.request,
            operation="Получение списка пользователей"
        ) or []
        
        return {"users": users}
```

### Способ 3: Ручная обработка

```python
from apps.common.api_error_handler import APIErrorHandler

class ManualListView(TemplateView):
    template_name = "users/list.html"
    
    def get_context_data(self, **kwargs):
        users = []
        
        try:
            users = self.users_api.list_users()
        except SyncServerAPIError as exc:
            APIErrorHandler.handle_api_error(
                self.request, exc, "получении списка пользователей"
            )
        except Exception as exc:
            APIErrorHandler.handle_generic_error(
                self.request, exc, "получении списка пользователей"
            )
        
        return {"users": users}
```

## Интеграция с существующими представлениями

### Операции:

```python
# apps/operations/views.py
@handle_api_errors(operation="Получение списка операций")
def get(self, request, *args, **kwargs):
    # Существующая логика
    pass
```

### Балансы:

```python
# apps/balances/views.py
@handle_api_errors(operation="Получение списка остатков")
def get(self, request, *args, **kwargs):
    # Существующая логика
    pass
```

### Пользователи:

```python
# apps/users/views.py
@handle_api_errors(operation="Создание пользователя")
def post(self, request, *args, **kwargs):
    # Существующая логика
    pass
```

## Настройка

### Конфигурация логирования:

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': '/var/log/django/api_errors.log',
        },
    },
    'loggers': {
        'apps.common.api_error_handler': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
```

### Настройка повторных попыток:

```python
# Декоратор
@handle_api_errors(
    retry_transient=True,
    max_retries=5,  # Увеличить количество попыток
    delay=2.0,      # Увеличить начальную задержку
    backoff=1.5     # Уменьшить множитель
)

# Или вручную
retry_func = APIErrorHandler.retry_on_transient_error(
    func,
    max_retries=5,
    delay=2.0,
    backoff=1.5
)
```

## Тестирование

### Модульное тестирование:

```python
from django.test import TestCase
from apps.common.api_error_handler import APIErrorHandler
from apps.sync_client.exceptions import SyncAuthError

class APIErrorHandlerTestCase(TestCase):
    def test_handle_auth_error(self):
        request = self.create_mock_request()
        error = SyncAuthError("Invalid token", status_code=401)
        
        APIErrorHandler.handle_api_error(
            request, error, operation="Test operation"
        )
        
        # Проверить сообщение пользователю
        messages = list(request._messages)
        self.assertIn("Ошибка аутентификации", str(messages[0]))
```

### Интеграционное тестирование:

```python
class ViewsWithErrorHandlingTestCase(TestCase):
    def test_view_with_api_error(self):
        # Mock API для возврата ошибки
        with patch('apps.sync_client.users_api.UsersAPI.list_users') as mock:
            mock.side_effect = SyncAuthError("Invalid token")
            
            response = self.client.get('/users/')
            
            # Проверить статус ответа
            self.assertEqual(response.status_code, 302)  # Перенаправление
            
            # Проверить сообщение
            self.assertRedirects(response, '/')
```

## Мониторинг

### Ключевые метрики:

1. **Количество ошибок по типам**
2. **Время ответа API**
3. **Успешность повторных попыток**
4. **Частота временных ошибок**

### Алёрты:

1. **Высокий уровень ошибок 5xx**
2. **Многократные неудачные повторные попытки**
3. **Длительные периоды недоступности**

## Расширение

### Добавление новых типов ошибок:

```python
from apps.sync_client.exceptions import SyncServerAPIError

class CustomBusinessError(SyncServerAPIError):
    """Кастомная бизнес-ошибка"""
    pass

# Расширение обработчика
class ExtendedAPIErrorHandler(APIErrorHandler):
    @staticmethod
    def handle_api_error(request, error, operation="", context=None):
        if isinstance(error, CustomBusinessError):
            # Специальная обработка
            messages.error(request, "Кастомная бизнес-ошибка")
            logger.warning(f"Custom business error: {operation}", extra=context)
        else:
            # Стандартная обработка
            super().handle_api_error(request, error, operation, context)
```

### Кастомизация сообщений:

```python
# settings.py
API_ERROR_MESSAGES = {
    'SyncAuthError': 'Пожалуйста, проверьте ваши учетные данные.',
    'SyncForbiddenError': 'Требуется дополнительная авторизация.',
    # ...
}

# В обработчике
user_message = settings.API_ERROR_MESSAGES.get(
    error.__class__.__name__,
    "Произошла непредвиденная ошибка."
)
```

## Заключение

Унифицированная обработка ошибок API обеспечивает:

1. **Согласованность** - единый подход во всех представлениях
2. **Безопасность** - защита от утечки информации
3. **Удобство** - понятные сообщения для пользователей
4. **Надёжность** - грациозная обработка сбоев
5. **Мониторинг** - детальное логирование для отладки

Использование этого модуля значительно упрощает разработку и поддержку представлений, работающих с SyncServer API.