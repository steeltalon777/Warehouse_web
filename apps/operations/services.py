from __future__ import annotations

import logging
from typing import Any

from apps.catalog_cache.services import CatalogCacheSyncService, CatalogLookupService
from apps.catalog.services import CatalogService
from apps.common.permissions import get_user_role, is_observer
from apps.operations.constants import OPERATION_STATUS_META, OPERATION_TYPE_LABELS, OPERATION_TYPE_META
from apps.sync_client.client import SyncServerClient

logger = logging.getLogger(__name__)


class OperationPageService:
    def __init__(self, client: SyncServerClient, *, request=None) -> None:
        self.client = client
        self.request = request
        self.catalog = CatalogService(client)
        self.catalog_lookup = CatalogLookupService()

    def get_available_sites(self) -> list[dict[str, Any]]:
        response = self.client.get("/auth/sites")
        sites = response.get("available_sites", []) if isinstance(response, dict) else []
        normalized: list[dict[str, Any]] = []
        for site in sites:
            permissions = site.get("permissions") or {}
            try:
                site_id = int(site.get("site_id"))
            except (TypeError, ValueError):
                continue
            normalized.append(
                {
                    "site_id": site_id,
                    "name": str(site.get("name") or site.get("code") or site_id),
                    "code": str(site.get("code") or ""),
                    "can_operate": bool(permissions.get("can_operate")),
                    "can_view": bool(permissions.get("can_view", True)),
                }
            )
        normalized.sort(key=lambda site: site["name"].lower())
        return normalized

    def get_operate_sites(self) -> list[dict[str, Any]]:
        return [site for site in self.get_available_sites() if site["can_operate"]]

    def get_current_role(self) -> str:
        request_user = getattr(self.request, "user", None)
        if request_user is not None and getattr(request_user, "is_superuser", False):
            return "root"
        return str(get_user_role(request_user) or "")

    def get_fixed_operating_site_id(self) -> int | None:
        role = self.get_current_role()
        if role != "storekeeper":
            return None

        try:
            default_site_id = getattr(self.request.user.sync_binding, "default_site_id", "")
        except Exception:
            return None
        return self._to_int(default_site_id)

    def can_choose_source_site(self) -> bool:
        return self.get_current_role() in {"root", "chief_storekeeper"}

    def search_items(self, query: str, *, limit: int = 12) -> list[dict[str, Any]]:
        normalized_limit = max(int(limit or 12), 1)
        cached_items = self.catalog_lookup.search_items(query, limit=normalized_limit)
        if len(cached_items) >= normalized_limit:
            return cached_items

        remote_items = self._search_remote_items(query, limit=normalized_limit)
        if remote_items:
            self._warm_catalog_cache(remote_items)

        return self._merge_search_items(cached_items, remote_items, limit=normalized_limit)

    def get_items_index(self) -> dict[int, dict[str, Any]]:
        result = self.catalog.list_items()
        if not result.ok:
            return {}

        index: dict[int, dict[str, Any]] = {}
        for item in result.data or []:
            item_id = self._to_int(item.get("id"))
            if item_id is None:
                continue
            index[item_id] = {
                "id": item_id,
                "name": str(item.get("name") or item.get("sku") or item_id),
                "sku": str(item.get("sku") or ""),
                "unit_symbol": str(item.get("unit_symbol") or item.get("unit") or ""),
            }
        return index

    def get_sites_index(self) -> dict[int, dict[str, Any]]:
        return {int(site["site_id"]): site for site in self.get_available_sites()}

    def present_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        items_index = self.get_items_index()
        sites_index = self.get_sites_index()
        return self._present_operation(operation, items_index=items_index, sites_index=sites_index)

    def present_operations(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items_index = self.get_items_index()
        sites_index = self.get_sites_index()
        return [
            self._present_operation(operation, items_index=items_index, sites_index=sites_index)
            for operation in operations
        ]

    def _search_remote_items(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        result = self.catalog.browse_items(search=query, page=1, page_size=max(limit, 25))
        if not result.ok:
            return []

        payload = result.data if isinstance(result.data, dict) else {}
        items = payload.get("items", []) if isinstance(payload, dict) else []
        serialized_items: list[dict[str, Any]] = []
        for item in items:
            serialized = self._serialize_search_item(item)
            if serialized is None or not serialized["is_active"]:
                continue
            serialized_items.append(serialized)
            if len(serialized_items) >= limit:
                break
        return serialized_items

    def _warm_catalog_cache(self, items: list[dict[str, Any]]) -> None:
        try:
            CatalogCacheSyncService(client=self.client).upsert_items(items)
        except Exception:
            logger.exception("Failed to warm local catalog cache from remote item search results.")

    @classmethod
    def _merge_search_items(
        cls,
        cached_items: list[dict[str, Any]],
        remote_items: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for item in [*cached_items, *remote_items]:
            item_id = cls._to_int(item.get("id") or item.get("item_id"))
            if item_id is None or item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            merged.append(item)
            if len(merged) >= limit:
                break
        return merged

    @classmethod
    def _serialize_search_item(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        item_id = cls._to_int(item.get("id") or item.get("item_id"))
        if item_id is None:
            return None

        return {
            "id": item_id,
            "name": str(item.get("name") or item.get("sku") or item_id),
            "sku": str(item.get("sku") or ""),
            "unit_symbol": str(item.get("unit_symbol") or item.get("unit_name") or item.get("unit") or ""),
            "category_name": str(item.get("category_name") or ""),
            "category_id": str(item.get("category_id") or ""),
            "is_active": bool(item.get("is_active", True)),
        }

    def _present_operation(
        self,
        operation: dict[str, Any],
        *,
        items_index: dict[int, dict[str, Any]],
        sites_index: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        status = str(operation.get("status") or "draft")
        status_meta = OPERATION_STATUS_META.get(status, {"label": status, "tone": "muted"})
        operation_type = str(operation.get("operation_type") or operation.get("type") or "")
        site_id = self._to_int(operation.get("site_id"))
        source_site_id = self._to_int(operation.get("source_site_id"))
        destination_site_id = self._to_int(operation.get("destination_site_id") or operation.get("target_site_id"))

        lines: list[dict[str, Any]] = []
        for line in operation.get("lines") or []:
            item_id = self._to_int(line.get("item_id"))
            item = items_index.get(item_id or -1, {})
            quantity = line.get("qty", line.get("quantity"))
            lines.append(
                {
                    "line_number": line.get("line_number"),
                    "item_id": item_id,
                    "item_name": item.get("name") or f"ТМЦ #{item_id}",
                    "sku": item.get("sku") or "—",
                    "unit_symbol": item.get("unit_symbol") or "—",
                    "quantity": quantity,
                    "comment": line.get("comment") or line.get("notes") or "",
                }
            )

        line_preview = [f"{line['item_name']} x {line['quantity']}" for line in lines[:2]]
        try:
            current_user_sync_id = getattr(self.request.user.sync_binding, "syncserver_user_id", None)
        except Exception:
            current_user_sync_id = None
        created_by_user_id = operation.get("created_by_user_id")
        author_label = "Вы" if current_user_sync_id and str(current_user_sync_id) == str(created_by_user_id) else str(created_by_user_id or "—")

        role = self.get_current_role()
        can_submit = status in {"draft", "created"} and role not in {"observer", "storekeeper"}
        can_cancel = (
            status in {"draft", "created", "pending", "submitted"}
            and not is_observer(getattr(self.request, "user", None))
            and (role != "storekeeper" or status == "draft")
        )

        return {
            **operation,
            "type_label": OPERATION_TYPE_LABELS.get(operation_type, operation_type or "Операция"),
            "status_label": str(status_meta["label"]),
            "status_tone": str(status_meta["tone"]),
            "site_name": self._site_name(sites_index, site_id),
            "source_site_name": self._site_name(sites_index, source_site_id),
            "destination_site_name": self._site_name(sites_index, destination_site_id),
            "lines": lines,
            "line_count": len(lines),
            "line_preview": ", ".join(line_preview),
            "author_label": author_label,
            "can_submit": can_submit,
            "can_cancel": can_cancel,
        }

    @staticmethod
    def operation_type_options() -> list[dict[str, Any]]:
        return [dict(item) for item in OPERATION_TYPE_META]

    @staticmethod
    def _site_name(sites_index: dict[int, dict[str, Any]], site_id: int | None) -> str:
        if site_id is None:
            return "—"
        site = sites_index.get(site_id)
        if not site:
            return str(site_id)
        return str(site.get("name") or site.get("code") or site_id)

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
