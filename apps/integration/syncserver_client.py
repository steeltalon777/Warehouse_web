from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings


class SyncServerError(Exception):
    def __init__(self, message: str, status_code: int | None = None, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class SyncServerClient:
    def __init__(self) -> None:
        self.base_url = settings.SYNC_SERVER_URL.rstrip("/")
        self.timeout = getattr(settings, "SYNC_SERVER_TIMEOUT", 10.0)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Site-Id": settings.SYNC_SITE_ID,
            "X-Device-Id": settings.SYNC_DEVICE_ID,
            "X-Device-Token": settings.SYNC_DEVICE_TOKEN,
            "X-Client-Version": settings.SYNC_CLIENT_VERSION,
        }

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, json=json, params=params, headers=self._headers())
        except httpx.RequestError as exc:
            raise SyncServerError("SyncServer временно недоступен.") from exc

        if response.status_code >= 400:
            payload: dict[str, Any] = {}
            try:
                payload = response.json()
            except ValueError:
                payload = {"detail": response.text or "Unknown error"}
            message = payload.get("detail") or "Ошибка SyncServer"
            raise SyncServerError(str(message), status_code=response.status_code, payload=payload)

        if response.status_code == 204:
            return None
        return response.json()

    def list_categories(self) -> list[dict[str, Any]]:
        return self._request("GET", "/catalog/categories")

    def categories_tree(self) -> list[dict[str, Any]]:
        return self._request("GET", "/catalog/categories/tree")

    def list_units(self) -> list[dict[str, Any]]:
        return self._request("GET", "/catalog/units")

    def list_items(self, *, category_id: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
        params = {"category_id": category_id, "search": search}
        clean = {k: v for k, v in params.items() if v}
        return self._request("GET", "/catalog/items", params=clean)

    def create_category(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/catalog/admin/categories", json=payload)

    def update_category(self, category_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/catalog/admin/categories/{category_id}", json=payload)

    def create_unit(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/catalog/admin/units", json=payload)

    def update_unit(self, unit_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/catalog/admin/units/{unit_id}", json=payload)

    def create_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/catalog/admin/items", json=payload)

    def update_item(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/catalog/admin/items/{item_id}", json=payload)
