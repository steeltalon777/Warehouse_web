from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.integration.syncserver_client import SyncServerClient, SyncServerError


@dataclass
class ServiceResult:
    ok: bool
    data: Any = None
    form_error: str | None = None
    not_found: bool = False
    server_unavailable: bool = False


class SyncUsersService:
    def __init__(self) -> None:
        self.client = SyncServerClient()

    def _handle_error(self, exc: SyncServerError) -> ServiceResult:
        if exc.status_code == 404:
            return ServiceResult(ok=False, not_found=True, form_error="Пользователь не найден.")
        if exc.status_code == 409:
            return ServiceResult(ok=False, form_error="Конфликт данных.")
        if exc.status_code == 400:
            return ServiceResult(ok=False, form_error=str(exc))
        if exc.status_code and exc.status_code >= 500:
            return ServiceResult(ok=False, server_unavailable=True, form_error="SyncServer временно недоступен.")
        return ServiceResult(ok=False, form_error=str(exc))

    def list_users(self) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.list_users())
        except SyncServerError as exc:
            return self._handle_error(exc)

    def create_user(self, payload: dict[str, Any]) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.create_user(payload))
        except SyncServerError as exc:
            return self._handle_error(exc)

    def update_user(self, user_id: str, payload: dict[str, Any]) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.update_user(user_id, payload))
        except SyncServerError as exc:
            return self._handle_error(exc)