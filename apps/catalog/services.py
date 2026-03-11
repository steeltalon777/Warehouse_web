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


class CatalogService:
    def __init__(self) -> None:
        self.client = SyncServerClient()

    def _handle_error(self, exc: SyncServerError) -> ServiceResult:
        if exc.status_code == 404:
            return ServiceResult(ok=False, not_found=True, form_error="Сущность не найдена в SyncServer.")
        if exc.status_code == 409:
            return ServiceResult(ok=False, form_error="Конфликт данных: дубль или недопустимая связь.")
        if exc.status_code == 400:
            return ServiceResult(ok=False, form_error=str(exc))
        if exc.status_code and exc.status_code >= 500:
            return ServiceResult(ok=False, server_unavailable=True, form_error="SyncServer временно недоступен.")
        return ServiceResult(ok=False, form_error=str(exc))

    def list_categories(self) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.list_categories())
        except SyncServerError as exc:
            return self._handle_error(exc)

    def categories_tree(self) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.categories_tree())
        except SyncServerError as exc:
            return self._handle_error(exc)

    def list_units(self) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.list_units())
        except SyncServerError as exc:
            return self._handle_error(exc)

    def list_items(self, *, category_id: str | None = None, search: str | None = None) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.list_items(category_id=category_id, search=search))
        except SyncServerError as exc:
            return self._handle_error(exc)

    def create_category(self, payload: dict[str, Any]) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.create_category(payload))
        except SyncServerError as exc:
            return self._handle_error(exc)

    def update_category(self, category_id: str, payload: dict[str, Any]) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.update_category(category_id, payload))
        except SyncServerError as exc:
            return self._handle_error(exc)

    def create_unit(self, payload: dict[str, Any]) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.create_unit(payload))
        except SyncServerError as exc:
            return self._handle_error(exc)

    def update_unit(self, unit_id: str, payload: dict[str, Any]) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.update_unit(unit_id, payload))
        except SyncServerError as exc:
            return self._handle_error(exc)

    def create_item(self, payload: dict[str, Any]) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.create_item(payload))
        except SyncServerError as exc:
            return self._handle_error(exc)

    def update_item(self, item_id: str, payload: dict[str, Any]) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=self.client.update_item(item_id, payload))
        except SyncServerError as exc:
            return self._handle_error(exc)
