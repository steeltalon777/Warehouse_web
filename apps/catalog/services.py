from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.sync_client.catalog_api import CatalogAPI
from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import SyncServerAPIError


@dataclass
class ServiceResult:
    ok: bool
    data: Any = None
    form_error: str | None = None
    not_found: bool = False


class CatalogService:
    def __init__(self, client: SyncServerClient | None = None) -> None:
        self.client = client or SyncServerClient(user_id="system", site_id="default")
        self.catalog_api = CatalogAPI(self.client)

    def _exec(self, fn, *args, **kwargs) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=fn(*args, **kwargs))
        except SyncServerAPIError as exc:
            return ServiceResult(
                ok=False,
                form_error=str(exc),
                not_found=exc.status_code == 404,
            )

    def list_categories(self) -> ServiceResult:
        return self._exec(
            lambda: self.client.post(
                "/business/catalog/categories",
                json={"updated_after": None, "limit": 500},
            ).get("categories", [])
        )

    def list_units(self) -> ServiceResult:
        return self._exec(
            lambda: self.client.post(
                "/business/catalog/units",
                json={"updated_after": None, "limit": 500},
            ).get("units", [])
        )

    def list_items(self, *, category_id: str | None = None, search: str | None = None) -> ServiceResult:
        def _load():
            items = self.client.post(
                "/business/catalog/items",
                json={"updated_after": None, "limit": 500},
            ).get("items", [])

            if category_id:
                items = [i for i in items if str(i.get("category_id")) == str(category_id)]

            if search:
                term = search.lower()
                items = [i for i in items if term in str(i.get("name", "")).lower()]

            return items

        return self._exec(_load)

    def categories_tree(self) -> ServiceResult:
        return self._exec(self.catalog_api.categories_tree)

    def create_category(self, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.create_category, payload)

    def update_category(self, category_id: str, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.client.patch, f"/catalog/admin/categories/{category_id}", json=payload)

    def create_unit(self, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.create_unit, payload)

    def update_unit(self, unit_id: str, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.client.patch, f"/catalog/admin/units/{unit_id}", json=payload)

    def create_item(self, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.create_item, payload)

    def update_item(self, item_id: str, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.client.patch, f"/catalog/admin/items/{item_id}", json=payload)