from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.integration.syncserver_client import SyncServerClient, SyncServerError


@dataclass
class ServiceResult:
    ok: bool
    data: Any = None
    form_error: str | None = None


class DomainService:
    def __init__(self) -> None:
        self.client = SyncServerClient()

    def _execute(self, func, *args, **kwargs) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=func(*args, **kwargs))
        except SyncServerError as exc:
            if exc.status_code and exc.status_code >= 500:
                return ServiceResult(ok=False, form_error="SyncServer временно недоступен.")
            return ServiceResult(ok=False, form_error=str(exc))

    # root/admin control panel
    def users(self) -> ServiceResult:
        return self._execute(self.client.list_users)

    def roles(self) -> ServiceResult:
        return self._execute(self.client.list_roles)

    def sites(self) -> ServiceResult:
        return self._execute(self.client.list_sites)

    def create_user(self, payload: dict[str, Any]) -> ServiceResult:
        return self._execute(self.client.create_user, payload)

    def update_user(self, user_id: str, payload: dict[str, Any]) -> ServiceResult:
        return self._execute(self.client.update_user, user_id, payload)

    # chief/storekeeper workflows
    def balances(self, *, search: str | None = None) -> ServiceResult:
        return self._execute(self.client.list_balances, search=search)

    def operations(self, *, search: str | None = None, limit: int = 50) -> ServiceResult:
        return self._execute(self.client.list_operations, search=search, limit=limit)

    def create_operation(self, payload: dict[str, Any]) -> ServiceResult:
        return self._execute(self.client.create_operation, payload)
