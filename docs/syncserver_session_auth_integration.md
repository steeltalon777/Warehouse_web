# Интеграция аутентификации SyncServer с Django Session

## Обзор

Эта интеграция позволяет хранить идентификацию пользователя SyncServer в Django сессии после успешного входа в Django. Это обеспечивает:

1. **Разделение ответственности**:
   - Django auth - технический слой для администраторов/сотрудников
   - SyncServer auth - доменная идентификация пользователей (токены, роли, склады)

2. **Автоматическую синхронизацию**:
   - После входа в Django автоматически получается контекст SyncServer
   - Идентификация сохраняется в сессии Django
   - При выходе из Django идентификация очищается

## Архитектура

### Ключевые компоненты

1. **`session_auth.py`** - Основной модуль интеграции
   - `store_syncserver_identity()` - получает и сохраняет идентификацию
   - `get_sync_identity()` - получает идентификацию из сессии
   - `clear_syncserver_identity()` - очищает идентификацию

2. **`simple_sync_signals.py`** - Сигналы Django
   - `user_logged_in` - вызывает `store_syncserver_identity()`
   - `user_logged_out` - вызывает `clear_syncserver_identity()`

3. **`SyncIdentity` dataclass** - Структурированная идентификация
   ```python
   SyncIdentity(
       user_token="...",          # Токен аутентификации SyncServer
       user_id="user-123",        # ID пользователя в SyncServer
       role="storekeeper",        # Роль пользователя
       is_root=False,             # Привилегии root
       available_sites=[...],     # Доступные склады
       default_site_id="site-456" # Склад по умолчанию
   )
   ```

### Поток данных

```
Django Login → Django Signals → store_syncserver_identity() → auth_api.get_context()
                                                              ↓
Django Session ← SyncIdentity ← Parse context response
```

## Использование

### В представлениях Django

```python
from apps.sync_client.session_auth import get_sync_identity

def my_view(request):
    # Получить идентификацию SyncServer
    identity = get_sync_identity(request)
    
    if identity:
        # Использовать идентификацию
        user_token = identity.user_token
        user_role = identity.role
        site_id = identity.site_id
        
        # Проверить доступ к складу
        if identity.has_site_access("site-789"):
            # Пользователь имеет доступ к складу
            pass
```

### В шаблонах Django

Добавить в `settings.py`:
```python
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'OPTIONS': {
            'context_processors': [
                ...
                'apps.users.simple_sync_signals.sync_identity_context',
            ],
        },
    },
]
```

Использование в шаблоне:
```html
{% if sync_identity %}
    <p>Пользователь SyncServer: {{ sync_identity.user_id }}</p>
    <p>Роль: {{ sync_identity.role }}</p>
    <p>Склад: {{ sync_identity.site_id }}</p>
{% endif %}
```

### Ручное управление

```python
from apps.sync_client.session_auth import (
    store_syncserver_identity,
    clear_syncserver_identity,
    get_sync_identity
)

# После успешного входа в Django
identity = store_syncserver_identity(request)

# При выходе из Django
clear_syncserver_identity(request)

# Проверить наличие идентификации
has_identity = get_sync_identity(request) is not None
```

## Данные в сессии

После успешной аутентификации в сессии сохраняются:

| Ключ сессии | Значение | Описание |
|-------------|----------|----------|
| `sync_user_token` | Строка | Токен аутентификации SyncServer |
| `sync_user_id` | Строка | ID пользователя в SyncServer |
| `sync_role` | Строка | Роль пользователя |
| `sync_is_root` | Boolean | Привилегии root |
| `sync_available_sites` | List[dict] | Доступные склады |
| `sync_default_site_id` | Строка (опционально) | Склад по умолчанию |
| `user_token` | Строка | Легаси-ключ для совместимости |

## Совместимость с SyncClient

Модуль `simple_client.py` автоматически использует токен из сессии:

1. Сначала проверяет `sync_user_token` (новая структура)
2. Затем проверяет `user_token` (легаси-ключ)
3. Добавляет токен в заголовок `X-User-Token`

## Обработка ошибок

### Грациозная деградация

Если получение идентификации SyncServer не удалось:
- Django аутентификация всё равно считается успешной
- В сессии не сохраняется идентификация SyncServer
- Пользователь может работать с базовыми функциями Django

### Логирование

Все операции логируются с разными уровнями:
- `INFO`: Успешные операции
- `WARNING`: Отсутствие данных или частичные сбои
- `ERROR`: Критические ошибки API
- `DEBUG`: Детальная отладка

## Настройка

### Обязательные настройки

В `settings.py` должны быть определены:

```python
# URL SyncServer API
SYNC_SERVER_URL = "http://syncserver.example.com/api/v1"

# Токен устройства для аутентификации
SYNC_DEVICE_TOKEN = "your-device-token-here"

# Таймаут запросов (секунды)
SYNC_SERVER_TIMEOUT = 10
```

### Регистрация сигналов

Сигналы автоматически регистрируются в `apps.users.apps.UsersConfig.ready()`.

## Тестирование

### Модульное тестирование

```python
from django.test import TestCase, RequestFactory
from apps.sync_client.session_auth import get_sync_identity

class SyncAuthTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get('/')
        self.request.session = {}
        
    def test_store_and_retrieve_identity(self):
        # Тестирование сохранения и получения идентификации
        pass
```

### Интеграционное тестирование

1. Успешный вход в Django → идентификация SyncServer в сессии
2. Выход из Django → очистка идентификации
3. Доступ к защищённым представлениям → проверка идентификации

## Устранение неполадок

### Проблема: Нет идентификации в сессии

**Возможные причины:**
1. Сигналы не зарегистрированы - проверьте `apps.py`
2. Ошибка API SyncServer - проверьте логи
3. Неправильные настройки - проверьте `SYNC_SERVER_URL` и `SYNC_DEVICE_TOKEN`

**Решение:**
```python
# Проверить регистрацию сигналов
python manage.py shell
>>> from django.apps import apps
>>> apps.get_app_config('users').ready()
```

### Проблема: SyncClient не получает токен

**Возможные причины:**
1. Токен не сохраняется в сессии
2. Неправильный ключ сессии

**Решение:**
```python
# Проверить содержимое сессии
print(request.session.keys())
print(request.session.get('sync_user_token'))
print(request.session.get('user_token'))
```

## Безопасность

### Защита данных

1. **Токены в сессии** - Django обеспечивает безопасное хранение сессий
2. **HTTPS** - Все запросы к SyncServer должны использовать HTTPS
3. **Валидация** - Проверка всех входящих данных от SyncServer

### Ограничения доступа

Используйте декораторы для защиты представлений:

```python
from django.contrib.auth.decorators import login_required
from apps.sync_client.session_auth import get_sync_identity

@login_required
def protected_view(request):
    identity = get_sync_identity(request)
    if not identity:
        return HttpResponseForbidden("SyncServer authentication required")
    
    # Логика представления
```

## Расширение

### Добавление полей

Для добавления новых полей в идентификацию:

1. Обновите `SyncIdentity` dataclass
2. Обновите `_store_identity_in_session()`
3. Обновите `get_sync_identity()`

### Кастомные сигналы

Для дополнительной логики создайте свои сигналы:

```python
from django.dispatch import Signal

sync_identity_stored = Signal()
sync_identity_cleared = Signal()

# Использование в обработчиках
sync_identity_stored.send(sender=None, request=request, identity=identity)
```