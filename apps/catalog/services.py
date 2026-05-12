from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

from apps.sync_client.catalog_api import CatalogAPI
from apps.sync_client.balances_api import BalancesAPI
from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import SyncServerAPIError


@dataclass
class ServiceResult:
    ok: bool
    data: Any = None
    form_error: str | None = None
    not_found: bool = False


class CatalogService:
    def __init__(self, client: SyncServerClient) -> None:
        self.client = client
        self.catalog_api = CatalogAPI(self.client)
        self.balances_api = BalancesAPI(self.client)

    def _exec(self, fn, *args, **kwargs) -> ServiceResult:
        try:
            return ServiceResult(ok=True, data=fn(*args, **kwargs))
        except SyncServerAPIError as exc:
            return ServiceResult(
                ok=False,
                form_error=str(exc),
                not_found=exc.status_code == 404,
            )

    def list_categories(self, *, limit: int = 1000) -> ServiceResult:
        return self._exec(self.catalog_api.list_categories, filters={"limit": limit})

    def list_units(self, *, limit: int = 1000) -> ServiceResult:
        return self._exec(self.catalog_api.list_units, filters={"limit": limit})

    def list_items(
        self,
        *,
        category_id: str | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> ServiceResult:
        def _load():
            items = self.catalog_api.list_items(filters={"limit": limit})

            if category_id:
                items = [i for i in items if str(i.get("category_id")) == str(category_id)]

            if search:
                term = search.lower()
                items = [i for i in items if term in str(i.get("name", "")).lower()]

            return items

        return self._exec(_load)

    def list_admin_categories(
        self,
        *,
        include_inactive: bool = True,
        include_deleted: bool = False,
        page_size: int = 100,
    ) -> ServiceResult:
        return self._exec(
            self._collect_admin_pages,
            self.catalog_api.list_admin_categories,
            filters={
                "include_inactive": include_inactive,
                "include_deleted": include_deleted,
            },
            page_size=page_size,
        )

    def list_admin_units(
        self,
        *,
        include_inactive: bool = True,
        include_deleted: bool = False,
        page_size: int = 100,
    ) -> ServiceResult:
        return self._exec(
            self._collect_admin_pages,
            self.catalog_api.list_admin_units,
            filters={
                "include_inactive": include_inactive,
                "include_deleted": include_deleted,
            },
            page_size=page_size,
        )

    def list_admin_items(
        self,
        *,
        include_inactive: bool = True,
        include_deleted: bool = False,
        page_size: int = 100,
    ) -> ServiceResult:
        return self._exec(
            self._collect_admin_pages,
            self.catalog_api.list_admin_items,
            filters={
                "include_inactive": include_inactive,
                "include_deleted": include_deleted,
            },
            page_size=page_size,
        )

    def browse_items(
        self,
        *,
        category_id: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ServiceResult:
        return self._exec(
            self._browse_items_page,
            category_id=category_id,
            search=search,
            page=page,
            page_size=page_size,
        )

    def browse_all_items(
        self,
        *,
        category_id: str | None = None,
        search: str | None = None,
        page_size: int = 100,
    ) -> ServiceResult:
        def _load():
            page = 1
            items: list[dict[str, Any]] = []

            while True:
                payload = self._browse_items_page(
                    category_id=category_id,
                    search=search,
                    page=page,
                    page_size=page_size,
                )
                page_items = payload.get("items", []) if isinstance(payload, dict) else []
                if not isinstance(page_items, list):
                    page_items = []
                items.extend(page_items)

                total_pages = _resolve_total_pages(payload, default_page_size=page_size)
                if page >= total_pages or not page_items:
                    break
                page += 1

            return items

        return self._exec(_load)

    def get_item(self, item_id: str) -> ServiceResult:
        return self._exec(self.catalog_api.get_item, item_id)

    def browse_categories(
        self,
        *,
        search: str | None = None,
        parent_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
        include: str | None = None,
        items_preview_limit: int = 5,
    ) -> ServiceResult:
        filters = {
            "search": search,
            "parent_id": parent_id,
            "page": page,
            "page_size": page_size,
            "include": include,
            "items_preview_limit": items_preview_limit,
        }
        return self._exec(self.catalog_api.browse_categories, filters=filters)

    def browse_category_items(
        self,
        category_id: str,
        *,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ServiceResult:
        filters = {
            "search": search,
            "page": page,
            "page_size": page_size,
        }
        return self._exec(self.catalog_api.browse_category_items, category_id, filters=filters)

    def categories_tree(self) -> ServiceResult:
        return self._exec(self.catalog_api.get_categories_tree)

    def _collect_admin_pages(
        self,
        list_page_fn,
        *,
        filters: dict[str, Any] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        page = 1
        items: list[dict[str, Any]] = []
        base_filters = dict(filters or {})

        while True:
            payload = list_page_fn(
                filters={
                    **base_filters,
                    "page": page,
                    "page_size": page_size,
                }
            )

            if isinstance(payload, list):
                page_items = payload
                total_pages = 1
            else:
                page_items = payload.get("items", []) if isinstance(payload, dict) else []
                total_pages = _resolve_total_pages(payload, default_page_size=page_size)

            if not isinstance(page_items, list):
                page_items = []
            items.extend(page_items)

            if page >= total_pages or not page_items:
                break
            page += 1

        return items

    def _browse_items_page(
        self,
        *,
        category_id: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        filters = {
            "search": search,
            "category_id": category_id,
            "page": page,
            "page_size": page_size,
        }
        return self.catalog_api.browse_items(filters=filters)

    def create_category(self, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.create_category, payload)

    def get_category(self, category_id: str) -> ServiceResult:
        return self._exec(self.catalog_api.get_category, category_id)

    def update_category(self, category_id: str, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.update_category, category_id, payload)

    def delete_category(self, category_id: str) -> ServiceResult:
        return self._exec(self.catalog_api.delete_category, category_id)

    def create_unit(self, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.create_unit, payload)

    def get_unit(self, unit_id: str) -> ServiceResult:
        return self._exec(self.catalog_api.get_unit, unit_id)

    def update_unit(self, unit_id: str, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.update_unit, unit_id, payload)

    def delete_unit(self, unit_id: str) -> ServiceResult:
        return self._exec(self.catalog_api.delete_unit, unit_id)

    def create_item(self, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.create_item, payload)

    def update_item(self, item_id: str, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.update_item, item_id, payload)

    def delete_item(self, item_id: str) -> ServiceResult:
        return self._exec(self.catalog_api.delete_item, item_id)

    def merge_items(self, source_id, target_id, comment=None) -> ServiceResult:
        payload = {
            "source_item_id": int(source_id),
            "target_item_id": int(target_id),
            "comment": comment,
        }
        return self._exec(self.catalog_api.merge_items, payload)

    def merge_categories(self, source_id, target_id, comment=None) -> ServiceResult:
        payload = {
            "source_category_id": int(source_id),
            "target_category_id": int(target_id),
            "comment": comment,
        }
        return self._exec(self.catalog_api.merge_categories, payload)

    def split_item(self, payload: dict[str, Any]) -> ServiceResult:
        return self._exec(self.catalog_api.split_item, payload)

    def get_item_balances(self, item_id: str | int) -> ServiceResult:
        return self._exec(self.balances_api.get_balances_by_item, item_id)


def _resolve_total_pages(payload: dict[str, Any] | None, *, default_page_size: int) -> int:
    if not isinstance(payload, dict):
        return 1

    try:
        total_pages = int(payload.get("total_pages") or 0)
    except (TypeError, ValueError):
        total_pages = 0
    if total_pages > 0:
        return total_pages

    try:
        total_count = int(payload.get("total_count") or 0)
    except (TypeError, ValueError):
        total_count = 0

    try:
        page_size = int(payload.get("page_size") or default_page_size or 1)
    except (TypeError, ValueError):
        page_size = default_page_size or 1

    if total_count <= 0 or page_size <= 0:
        return 1
    return max(1, ceil(total_count / page_size))
