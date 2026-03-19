"""
Примеры использования AuthAPI модуля.

Этот файл содержит примеры кода для демонстрации использования
AuthAPI клиента. Не предназначен для использования в production.
"""

from django.http import HttpRequest
from apps.sync_client import AuthAPI, get_auth_api, SyncAPIError


def example_basic_usage(request: HttpRequest):
    """
    Базовое использование AuthAPI.
    
    Args:
        request: Django HttpRequest объект с сессией
    """
    print("=== Пример 1: Базовое использование ===")
    
    # Способ 1: Создание экземпляра напрямую
    auth_api = AuthAPI()
    
    # Способ 2: Использование фабричной функции
    auth_api = get_auth_api()
    
    try:
        # Получение информации о текущем пользователе
        user_info = auth_api.get_me(request)
        print(f"Пользователь: {user_info.get('username')}")
        print(f"Email: {user_info.get('email')}")
        print(f"ID: {user_info.get('id')}")
        
    except SyncAPIError as e:
        print(f"Ошибка при получении информации о пользователе: {e.message}")
    
    print()


def example_get_context(request: HttpRequest):
    """
    Пример получения контекста аутентификации.
    
    Args:
        request: Django HttpRequest объект с сессией
    """
    print("=== Пример 2: Получение контекста аутентификации ===")
    
    auth_api = get_auth_api()
    
    try:
        context = auth_api.get_context(request)
        
        user = context.get('user', {})
        site = context.get('site', {})
        
        print(f"Пользователь: {user.get('username')} (ID: {user.get('id')})")
        print(f"Сайт: {site.get('name')} (ID: {site.get('id')})")
        print(f"Роль: {context.get('role')}")
        
    except SyncAPIError as e:
        print(f"Ошибка при получении контекста: {e.message}")
    
    print()


def example_get_sites(request: HttpRequest):
    """
    Пример получения списка сайтов.
    
    Args:
        request: Django HttpRequest объект с сессией
    """
    print("=== Пример 3: Получение списка сайтов ===")
    
    auth_api = get_auth_api()
    
    try:
        sites = auth_api.get_sites(request)
        
        print(f"Доступно сайтов: {len(sites)}")
        
        for i, site in enumerate(sites, 1):
            print(f"{i}. {site.get('name')} (ID: {site.get('id')})")
            print(f"   Описание: {site.get('description', 'Нет описания')}")
            print(f"   Активен: {'Да' if site.get('is_active') else 'Нет'}")
            print()
        
    except SyncAPIError as e:
        print(f"Ошибка при получении списка сайтов: {e.message}")
    
    print()


def example_sync_user(request: HttpRequest):
    """
    Пример синхронизации пользователя.
    
    Args:
        request: Django HttpRequest объект с сессией
    """
    print("=== Пример 4: Синхронизация пользователя ===")
    
    auth_api = get_auth_api()
    
    # Пример данных пользователя для синхронизации
    user_payload = {
        "username": "ivanov_ivan",
        "email": "ivan.ivanov@example.com",
        "full_name": "Иван Иванов",
        "phone": "+7 999 123-45-67",
        "metadata": {
            "department": "Отдел продаж",
            "position": "Менеджер"
        }
    }
    
    try:
        result = auth_api.sync_user(request, user_payload)
        
        print(f"Синхронизация успешна!")
        print(f"ID пользователя: {result.get('user_id')}")
        print(f"Статус: {result.get('status')}")
        print(f"Сообщение: {result.get('message', 'Нет сообщения')}")
        
        if result.get('warnings'):
            print(f"Предупреждения: {result['warnings']}")
        
    except SyncAPIError as e:
        print(f"Ошибка при синхронизации пользователя: {e.message}")
        if e.response_data:
            print(f"Детали ошибки: {e.response_data}")
    
    print()


def example_token_validation(request: HttpRequest):
    """
    Пример валидации токена.
    
    Args:
        request: Django HttpRequest объект с сессией
    """
    print("=== Пример 5: Валидация токена ===")
    
    auth_api = get_auth_api()
    
    try:
        is_valid = auth_api.validate_token(request)
        
        if is_valid:
            print("✅ Токен действителен")
            
            # Получаем дополнительную информацию
            user_info = auth_api.get_me(request)
            print(f"   Пользователь: {user_info.get('username')}")
            
        else:
            print("❌ Токен недействителен или отсутствует")
            
    except SyncAPIError as e:
        print(f"Ошибка при валидации токена: {e.message}")
    
    print()


def example_error_handling(request: HttpRequest):
    """
    Пример обработки ошибок.
    
    Args:
        request: Django HttpRequest объект с сессией
    """
    print("=== Пример 6: Обработка ошибок ===")
    
    auth_api = get_auth_api()
    
    try:
        # Попытка выполнить запрос с неверными данными
        result = auth_api.sync_user(request, {})
        
    except SyncAPIError as e:
        print(f"Произошла ошибка API:")
        print(f"  Сообщение: {e.message}")
        print(f"  Код статуса: {e.status_code}")
        print(f"  Метод: {getattr(e, 'method', 'N/A')}")
        print(f"  Путь: {getattr(e, 'path', 'N/A')}")
        
        if e.response_data:
            print(f"  Данные ответа: {e.response_data}")
        
        # Обработка конкретных типов ошибок
        if e.status_code == 401:
            print("  Действие: Требуется повторная аутентификация")
        elif e.status_code == 403:
            print("  Действие: Проверьте права доступа")
        elif e.status_code == 404:
            print("  Действие: Ресурс не найден")
        elif e.status_code == 422:
            print("  Действие: Проверьте входные данные")
        else:
            print("  Действие: Обратитесь к администратору")
    
    print()


def example_custom_client(request: HttpRequest):
    """
    Пример использования кастомного клиента.
    
    Args:
        request: Django HttpRequest объект с сессией
    """
    print("=== Пример 7: Кастомный клиент ===")
    
    from apps.sync_client import SyncClient
    
    # Создаем клиент с кастомным таймаутом
    custom_client = SyncClient(timeout=5.0)
    
    # Передаем кастомный клиент в AuthAPI
    auth_api = AuthAPI(client=custom_client)
    
    try:
        user_info = auth_api.get_me(request)
        print(f"Использован кастомный клиент с таймаутом 5 секунд")
        print(f"Пользователь: {user_info.get('username')}")
        
    except SyncAPIError as e:
        print(f"Ошибка: {e.message}")
    
    print()


def run_all_examples(request: HttpRequest):
    """
    Запуск всех примеров.
    
    Args:
        request: Django HttpRequest объект с сессией
    """
    print("=" * 60)
    print("ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ AUTHAPI")
    print("=" * 60)
    print()
    
    example_basic_usage(request)
    example_get_context(request)
    example_get_sites(request)
    example_sync_user(request)
    example_token_validation(request)
    example_error_handling(request)
    example_custom_client(request)
    
    print("=" * 60)
    print("ВСЕ ПРИМЕРЫ ВЫПОЛНЕНЫ")
    print("=" * 60)


# Пример использования в Django View
class ExampleAuthView:
    """
    Пример использования AuthAPI в Django View.
    """
    
    @staticmethod
    def get_user_profile(request: HttpRequest):
        """
        Получение профиля пользователя.
        
        Args:
            request: Django HttpRequest
            
        Returns:
            dict: Данные профиля или ошибка
        """
        from django.http import JsonResponse
        from apps.sync_client import get_auth_api
        
        auth_api = get_auth_api()
        
        try:
            # Получаем информацию о пользователе
            user_info = auth_api.get_me(request)
            
            # Получаем контекст для дополнительной информации
            context = auth_api.get_context(request)
            
            # Формируем ответ
            profile_data = {
                "success": True,
                "user": user_info,
                "site": context.get("site", {}),
                "role": context.get("role"),
            }
            
            return JsonResponse(profile_data)
            
        except SyncAPIError as e:
            return JsonResponse({
                "success": False,
                "error": e.message,
                "status_code": e.status_code
            }, status=e.status_code or 500)
    
    @staticmethod
    def sync_user_profile(request: HttpRequest):
        """
        Синхронизация профиля пользователя.
        
        Args:
            request: Django HttpRequest
            
        Returns:
            dict: Результат синхронизации
        """
        from django.http import JsonResponse
        from apps.sync_client import get_auth_api
        
        # В реальном приложении данные будут приходить из формы
        user_data = {
            "full_name": request.POST.get("full_name", ""),
            "email": request.POST.get("email", ""),
            "phone": request.POST.get("phone", ""),
        }
        
        # Фильтруем пустые значения
        payload = {k: v for k, v in user_data.items() if v}
        
        if not payload:
            return JsonResponse({
                "success": False,
                "error": "Нет данных для обновления"
            }, status=400)
        
        auth_api = get_auth_api()
        
        try:
            result = auth_api.sync_user(request, payload)
            
            return JsonResponse({
                "success": True,
                "message": "Профиль успешно обновлен",
                "result": result
            })
            
        except SyncAPIError as e:
            return JsonResponse({
                "success": False,
                "error": e.message,
                "details": e.response_data
            }, status=e.status_code or 500)


if __name__ == "__main__":
    print("Этот файл содержит примеры использования AuthAPI.")
    print("Для запуска примеров требуется Django HttpRequest объект.")
    print()
    print("Импортируйте функции в ваш Django проект:")
    print("  from apps.sync_client.auth_examples import ExampleAuthView")
    print()