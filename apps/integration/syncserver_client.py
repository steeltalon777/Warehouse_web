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

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
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
        response = self._request("POST", "/catalog/categories", json={"updated_after": None, "limit": 100})
        return response.get("categories", [])

    def list_units(self) -> list[dict[str, Any]]:
        response = self._request("POST", "/catalog/units", json={"updated_after": None, "limit": 100})
        return response.get("units", [])

    def list_items(self, *, category_id: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
        response = self._request("POST", "/catalog/items", json={"updated_after": None, "limit": 100})
        items = response.get("items", [])

        if category_id:
            items = [item for item in items if str(item.get("category_id")) == str(category_id)]

        if search:
            search_lower = search.lower()
            items = [item for item in items if search_lower in str(item.get("name", "")).lower()]

        return items

    def categories_tree(self) -> list[dict[str, Any]]:
        return self._request("GET", "/catalog/categories/tree")

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

    # Users / roles / sites
    def list_users(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/users")
        return response.get("users", response if isinstance(response, list) else [])

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/users", json=payload)

    def update_user(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/users/{user_id}", json=payload)

    def list_roles(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/roles")
        return response.get("roles", response if isinstance(response, list) else [])

    def list_sites(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/sites")
        return response.get("sites", response if isinstance(response, list) else [])

    # Operations / balances
    def list_balances(self, *, search: str | None = None) -> list[dict[str, Any]]:
        params = {"search": search} if search else None
        response = self._request("GET", "/balances", params=params)
        return response.get("balances", response if isinstance(response, list) else [])

    def list_operations(self, *, search: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params = {"search": search, "limit": limit}
        response = self._request("GET", "/operations", params=params)
        return response.get("operations", response if isinstance(response, list) else [])

    def create_operation(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/operations", json=payload)
