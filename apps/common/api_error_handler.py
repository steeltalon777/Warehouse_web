"""
Unified API error handling for SyncServer integration.

This module provides decorators and utilities for consistent error handling
across all views that interact with SyncServer API.

Features:
1. Centralized exception handling
2. User-friendly error messages
3. Comprehensive logging
4. Safe fallback behavior
5. Optional retry for transient errors
"""

import logging
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, cast

from django.contrib import messages
from django.http import HttpRequest, HttpResponse

from apps.sync_client.exceptions import (
    SyncAuthError,
    SyncBackendUnavailable,
    SyncConflictError,
    SyncForbiddenError,
    SyncNotFoundError,
    SyncServerAPIError,
    SyncServerInternalError,
    SyncValidationError,
)

logger = logging.getLogger(__name__)

# Type variable for function return type
F = TypeVar('F', bound=Callable[..., Any])


class APIErrorHandler:
    """
    Unified error handler for SyncServer API operations.
    
    This class provides methods for handling different types of API errors
    with consistent logging and user messaging.
    """
    
    @staticmethod
    def handle_api_error(
        request: HttpRequest,
        error: SyncServerAPIError,
        operation: str = "API операция",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Handle SyncServer API error with logging and user messaging.
        
        Args:
            request: Django HttpRequest object
            error: SyncServerAPIError instance
            operation: Description of the operation that failed
            context: Additional context for logging
        """
        context = context or {}
        
        # Extract error details
        error_details = {
            "operation": operation,
            "error_type": error.__class__.__name__,
            "status_code": error.status_code,
            "method": error.method,
            "path": error.path,
            "error_message": str(error),
            **context,
        }
        
        # Log error with appropriate level
        if isinstance(error, SyncBackendUnavailable):
            logger.error(f"SyncServer недоступен: {operation}", extra=error_details)
            user_message = "Сервер синхронизации временно недоступен. Пожалуйста, попробуйте позже."
        elif isinstance(error, SyncAuthError):
            logger.warning(f"Ошибка аутентификации: {operation}", extra=error_details)
            user_message = "Ошибка аутентификации. Пожалуйста, войдите снова."
        elif isinstance(error, SyncForbiddenError):
            logger.warning(f"Доступ запрещён: {operation}", extra=error_details)
            user_message = "У вас недостаточно прав для выполнения этой операции."
        elif isinstance(error, SyncNotFoundError):
            logger.warning(f"Ресурс не найден: {operation}", extra=error_details)
            user_message = "Запрашиваемый ресурс не найден."
        elif isinstance(error, SyncValidationError):
            logger.warning(f"Ошибка валидации: {operation}", extra=error_details)
            # Try to extract validation errors from payload
            if error.payload and "errors" in error.payload:
                user_message = f"Ошибка валидации: {error.payload['errors']}"
            else:
                user_message = "Ошибка в данных запроса. Проверьте введённые данные."
        elif isinstance(error, SyncConflictError):
            logger.warning(f"Конфликт данных: {operation}", extra=error_details)
            user_message = "Конфликт данных. Возможно, ресурс был изменён другим пользователем."
        elif isinstance(error, SyncServerInternalError):
            logger.error(f"Внутренняя ошибка SyncServer: {operation}", extra=error_details)
            user_message = "Внутренняя ошибка сервера. Пожалуйста, попробуйте позже."
        else:
            logger.error(f"Неизвестная ошибка SyncServer: {operation}", extra=error_details)
            user_message = "Произошла неизвестная ошибка. Пожалуйста, попробуйте позже."
        
        # Add error message for user
        messages.error(request, user_message)
        
        # Log full error details for debugging
        logger.debug(f"Полные детали ошибки: {error_details}")
    
    @staticmethod
    def handle_generic_error(
        request: HttpRequest,
        error: Exception,
        operation: str = "операция",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Handle generic (non-API) errors.
        
        Args:
            request: Django HttpRequest object
            error: Exception instance
            operation: Description of the operation that failed
            context: Additional context for logging
        """
        context = context or {}
        
        error_details = {
            "operation": operation,
            "error_type": error.__class__.__name__,
            "error_message": str(error),
            **context,
        }
        
        # Log the error
        logger.exception(f"Неожиданная ошибка при выполнении {operation}", extra=error_details)
        
        # Show generic error message to user (no traceback)
        messages.error(
            request,
            "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
        )
    
    @staticmethod
    def retry_on_transient_error(
        func: Callable[..., Any],
        max_retries: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0,
    ) -> Callable[..., Any]:
        """
        Decorator for retrying functions on transient errors.
        
        Args:
            func: Function to decorate
            max_retries: Maximum number of retry attempts
            delay: Initial delay between retries in seconds
            backoff: Multiplier for delay after each retry
            
        Returns:
            Decorated function with retry logic
        """
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (SyncBackendUnavailable, SyncServerInternalError) as e:
                    last_exception = e
                    
                    # Check if we should retry
                    if attempt < max_retries:
                        logger.warning(
                            f"Попытка {attempt + 1}/{max_retries} не удалась, "
                            f"повтор через {current_delay}с: {e}"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"Все {max_retries} попыток не удались",
                            extra={"error": str(e)}
                        )
                        raise
                except Exception as e:
                    # Don't retry on other errors
                    raise
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected state in retry decorator")
        
        return wrapper


def handle_api_errors(
    operation: str = "API операция",
    log_context: Optional[dict[str, Any]] = None,
    retry_transient: bool = False,
    max_retries: int = 3,
) -> Callable[[F], F]:
    """
    Decorator for handling API errors in view functions.
    
    Args:
        operation: Description of the operation for logging
        log_context: Additional context for logging
        retry_transient: Whether to retry on transient errors
        max_retries: Maximum retry attempts if retry_transient is True
        
    Returns:
        Decorated view function
    """
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapper(*args: Any, **kwargs: Any) -> HttpResponse:
            handler = APIErrorHandler()
            context = log_context or {}
            request: HttpRequest | None = None

            if args:
                first = args[0]
                if isinstance(first, HttpRequest):
                    request = first
                elif len(args) > 1 and isinstance(args[1], HttpRequest):
                    request = args[1]

            if request is None:
                raise TypeError("handle_api_errors could not resolve HttpRequest argument")
            
            try:
                # Apply retry logic if requested
                if retry_transient:
                    retry_func = handler.retry_on_transient_error(
                        view_func,
                        max_retries=max_retries
                    )
                    return retry_func(*args, **kwargs)
                else:
                    return view_func(*args, **kwargs)
                    
            except SyncServerAPIError as e:
                # Handle SyncServer API errors
                handler.handle_api_error(request, e, operation, context)
                
                # Return appropriate response based on error type
                if isinstance(e, SyncAuthError):
                    # Redirect to login for auth errors
                    from django.shortcuts import redirect
                    from django.urls import reverse
                    return redirect(reverse('login'))
                elif isinstance(e, SyncNotFoundError):
                    # Return 404 for not found errors
                    from django.shortcuts import render
                    return render(request, '404.html', status=404)
                else:
                    # For other errors, re-raise to let view handle it
                    # or return to previous page
                    from django.shortcuts import redirect
                    return redirect(request.META.get('HTTP_REFERER', '/'))
                    
            except Exception as e:
                # Handle generic errors
                handler.handle_generic_error(request, e, operation, context)
                
                # Return to previous page or home
                from django.shortcuts import redirect
                return redirect(request.META.get('HTTP_REFERER', '/'))
        
        return cast(F, wrapper)
    
    return decorator


class APIErrorHandlingMixin:
    """
    Mixin for class-based views to add API error handling.
    
    Usage:
        class MyView(APIErrorHandlingMixin, View):
            @handle_api_errors(operation="Получение данных")
            def get(self, request):
                # Your view logic here
    """
    
    def handle_api_error(self, error: SyncServerAPIError, operation: str = "") -> None:
        """
        Handle API error in class-based view.
        
        Args:
            error: SyncServerAPIError instance
            operation: Description of the operation
        """
        APIErrorHandler.handle_api_error(self.request, error, operation)
    
    def handle_generic_error(self, error: Exception, operation: str = "") -> None:
        """
        Handle generic error in class-based view.
        
        Args:
            error: Exception instance
            operation: Description of the operation
        """
        APIErrorHandler.handle_generic_error(self.request, error, operation)


# Convenience functions for common operations
def safe_api_call(
    api_func: Callable[..., Any],
    request: HttpRequest,
    operation: str = "API вызов",
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Safely call an API function with error handling.
    
    Args:
        api_func: API function to call
        request: Django HttpRequest object
        operation: Description of the operation
        *args: Arguments to pass to api_func
        **kwargs: Keyword arguments to pass to api_func
        
    Returns:
        Result of api_func or None if error occurred
    """
    handler = APIErrorHandler()
    
    try:
        return api_func(*args, **kwargs)
    except SyncServerAPIError as e:
        handler.handle_api_error(request, e, operation)
        return None
    except Exception as e:
        handler.handle_generic_error(request, e, operation)
        return None


def log_api_call(
    method: str,
    path: str,
    status_code: Optional[int] = None,
    response_data: Optional[dict[str, Any]] = None,
    context: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log API call details for monitoring and debugging.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: API endpoint path
        status_code: HTTP status code
        response_data: Response data (for debugging)
        context: Additional context for logging
    """
    log_data = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "has_response": response_data is not None,
        **(context or {}),
    }
    
    if status_code and status_code >= 400:
        logger.warning(f"API запрос завершился с ошибкой", extra=log_data)
        if response_data:
            logger.debug(f"Ответ API: {response_data}")
    else:
        logger.debug(f"API запрос выполнен", extra=log_data)
