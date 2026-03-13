from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import (
    SyncAuthError,
    SyncBackendUnavailable,
    SyncConflictError,
    SyncForbiddenError,
    SyncNotFoundError,
    SyncServerAPIError,
    SyncValidationError,
)


@dataclass
class ServiceResult:
    ok: bool
    data: Any = None
    form_error: str | None = None
    not_found: bool = False
    forbidden: bool = False
    auth_error: bool = False
    conflict: bool = False
    backend_unavailable: bool = False
    validation_error: bool = False


class DomainService:
    """
    Canonical domain-facing service layer for Django SSR client flows.

    IMPORTANT:
    - Do NOT use legacy /users, /roles, /sites endpoints.
    - Do NOT use apps.integration.* clients.
    - Root/admin pages for sites/devices/access live in apps.admin_panel via AdminAPI.
    - User CRUD is intentionally not implemented here until SyncServer exposes
      canonical endpoints for it.
    """

    def __init__(self, client: SyncServerClient | None = None) -> None:
        self.client = client or SyncServerClient()

    def _execute(self, func, *args, **kwargs) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=func(*args, **kwargs))
        except SyncBackendUnavailable:
            return ServiceResult(
                ok=False,
                backend_unavailable=True,
                form_error="SyncServer недоступен.",
            )
        except SyncAuthError as exc:
            return ServiceResult(
                ok=False,
                auth_error=True,
                form_error=str(exc) or "Ошибка авторизации в SyncServer.",
            )
        except SyncForbiddenError as exc:
            return ServiceResult(
                ok=False,
                forbidden=True,
                form_error=str(exc) or "Недостаточно прав для выполнения запроса в SyncServer.",
            )
        except SyncNotFoundError as exc:
            return ServiceResult(
                ok=False,
                not_found=True,
                form_error=str(exc) or "Запрошенный endpoint или сущность не найдены в SyncServer.",
            )
        except SyncValidationError as exc:
            return ServiceResult(
                ok=False,
                validation_error=True,
                form_error=str(exc) or "SyncServer отклонил запрос из-за ошибки в данных.",
            )
        except SyncConflictError as exc:
            return ServiceResult(
                ok=False,
                conflict=True,
                form_error=str(exc) or "Конфликт данных в SyncServer.",
            )
        except SyncServerAPIError as exc:
            return ServiceResult(ok=False, form_error=str(exc) or "Ошибка SyncServer.")

    # ------------------------------------------------------------------
    # Legacy root user-management: intentionally disabled
    # ------------------------------------------------------------------
    def users(self) -> ServiceResult:
        return ServiceResult(
            ok=False,
            not_found=True,
            form_error="Управление пользователями через legacy /users API отключено. Используй admin pages sites/devices/access или дождись нового user API в SyncServer.",
        )

    def roles(self) -> ServiceResult:
        return ServiceResult(
            ok=False,
            not_found=True,
            form_error="Legacy endpoint /roles отключён и не используется.",
        )

    def sites(self) -> ServiceResult:
        return ServiceResult(
            ok=False,
            not_found=True,
            form_error="Legacy endpoint /sites отключён. Для сайтов используй admin panel -> /api/v1/admin/sites.",
        )

    def create_user(self, payload: dict[str, Any]) -> ServiceResult:
        return ServiceResult(
            ok=False,
            not_found=True,
            form_error="Создание пользователей через legacy /users API отключено.",
        )

    def update_user(self, user_id: str, payload: dict[str, Any]) -> ServiceResult:
        return ServiceResult(
            ok=False,
            not_found=True,
            form_error="Редактирование пользователей через legacy /users API отключено.",
        )

    # ------------------------------------------------------------------
    # Business flows
    # ------------------------------------------------------------------
    def balances(self, *, search: str | None = None) -> ServiceResult:
        def _load():
            params: dict[str, Any] = {}
            if search:
                params["search"] = search
            response = self.client.get("/balances/", params=params or None)
            if isinstance(response, dict):
                return response.get("balances", response.get("results", []))
            if isinstance(response, list):
                return response
            return []

        return self._execute(_load)

    def operations(self, *, search: str | None = None, limit: int = 50) -> ServiceResult:
        def _load():
            params: dict[str, Any] = {"limit": limit}
            if search:
                params["search"] = search
            response = self.client.get("/operations/", params=params)
            if isinstance(response, dict):
                return response.get("operations", response.get("results", []))
            if isinstance(response, list):
                return response
            return []

        return self._execute(_load)

    def create_operation(self, payload: dict[str, Any]) -> ServiceResult:
        return self._execute(self.client.post, "/operations/", json=payload)