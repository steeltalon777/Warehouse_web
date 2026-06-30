import json
from typing import Any

import structlog

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import DatabaseError
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _extract_pagination,
    _handle_sync_error,
    _ok,
    _error,
    _require_chief_or_root,
)
from apps.catalog_cache.services import CatalogCacheSyncService, CatalogLookupService
from apps.catalog.services import CatalogService
from apps.sync_client.balances_api import BalancesAPI
from apps.sync_client.catalog_api import CatalogAPI
from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import SyncServerAPIError

logger = structlog.get_logger()


def _catalog(request):
    return CatalogAPI(_build_client(request))


# ── Primary Read (cursor-based, sync-optimized) ───────────────


class ItemsView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            for key in ("updated_after", "limit", "site_id"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = client.get("/catalog/items", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class CategoriesView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            for key in ("updated_after", "limit", "site_id"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = client.get("/catalog/categories", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class CategoriesTreeView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            site_id = request.GET.get("site_id")
            if site_id:
                params["site_id"] = site_id
            data = client.get("/catalog/categories/tree", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class UnitsView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            for key in ("updated_after", "limit", "site_id"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = client.get("/catalog/units", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class CatalogSitesView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            is_active = request.GET.get("is_active")
            if is_active is not None:
                params["is_active"] = is_active
            data = client.get("/catalog/sites", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


# ── Browse Read (paginated, search) ───────────────────────────


class BrowseItemsView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _catalog(request)
            params: dict[str, Any] = {}
            for key in ("search", "category_id", "page", "page_size", "site_id"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.browse_items(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)



class ItemReadView(LoginRequiredMixin, View):
    def get(self, request, item_id):
        try:
            api = _catalog(request)
            data = api.get_item_read_model(str(item_id))
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class BrowseCategoriesView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _catalog(request)
            params: dict[str, Any] = {}
            for key in ("search", "parent_id", "page", "page_size", "include", "items_preview_limit", "site_id"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.browse_categories(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class BrowseCategoryItemsView(LoginRequiredMixin, View):
    def get(self, request, category_id):
        try:
            api = _catalog(request)
            params: dict[str, Any] = {}
            for key in ("search", "page", "page_size", "site_id"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.browse_category_items(category_id, filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class BrowseCategoryChildrenView(LoginRequiredMixin, View):
    def get(self, request, category_id):
        try:
            api = _catalog(request)
            params: dict[str, Any] = {}
            for key in ("page", "page_size", "include", "items_preview_limit", "site_id"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.browse_category_children(category_id, filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class BrowseCategoryParentChainView(LoginRequiredMixin, View):
    def get(self, request, category_id):
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            site_id = request.GET.get("site_id")
            if site_id:
                params["site_id"] = site_id
            data = client.get(f"/catalog/read/categories/{category_id}/parent-chain", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


# ── Admin Units ────────────────────────────────────────────────


class AdminUnitsListView(LoginRequiredMixin, View):
    def get(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            params = _extract_pagination(request)
            for key in ("include_inactive", "include_deleted"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_admin_units(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.create_unit(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class AdminUnitsBulkView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.bulk_create_units(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class AdminUnitDetailView(LoginRequiredMixin, View):
    def get(self, request, unit_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            data = api.get_unit(unit_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, unit_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.update_unit(unit_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

    def delete(self, request, unit_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            api.delete_unit(unit_id)
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


# ── Admin Categories ────────────────────────────────────────────


class AdminCategoriesListView(LoginRequiredMixin, View):
    def get(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            params = _extract_pagination(request)
            for key in ("include_inactive", "include_deleted"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_admin_categories(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.create_category(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class AdminCategoriesBulkView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.bulk_create_categories(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class AdminCategoryDetailView(LoginRequiredMixin, View):
    def get(self, request, category_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            data = api.get_category(category_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, category_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.update_category(category_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

    def delete(self, request, category_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            api.delete_category(category_id)
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


# ── Admin Items ──────────────────────────────────────────────────


class AdminItemsListView(LoginRequiredMixin, View):
    def get(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            params = _extract_pagination(request)
            for key in ("include_inactive", "include_deleted"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_admin_items(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.create_item(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class AdminItemDetailView(LoginRequiredMixin, View):
    def get(self, request, item_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            data = api.get_item(item_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, item_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.update_item(item_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

    def delete(self, request, item_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            api.delete_item(item_id)
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


# ── Admin Batch ─────────────────────────────────────────────────────


class AdminCatalogBatchView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _catalog(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.apply_catalog_batch(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


# ── Cached Search (cache-first, fallback, warm) ────────────────────


class CatalogCachedItemSearchView(LoginRequiredMixin, View):
    """BFF endpoint for cached item search - cache-first with remote fallback and cache warming."""

    def get(self, request):
        query = (request.GET.get("q") or "").strip()
        if len(query) < 2:
            return _ok({"results": []})

        try:
            limit = min(max(int(request.GET.get("limit") or 20), 1), 50)
        except (TypeError, ValueError):
            limit = 20

        source_site_id = request.GET.get("source_site_id") or ""
        include_balance = request.GET.get("include_balance", "").lower() in ("true", "1")

        try:
            cached_items = self._search_local_cache(query, limit=limit)
        except DatabaseError:
            logger.warning("Local catalog cache unavailable, falling back to remote search")
            cached_items = []

        if len(cached_items) >= limit:
            results = self._enrich_with_balances(request, cached_items, source_site_id) if include_balance and source_site_id else cached_items
            return _ok({"results": results})

        try:
            remote_items = self._search_remote_items(request, query, limit=limit)
        except SyncServerAPIError:
            logger.warning("Remote catalog search unavailable, using local cache results only")
            remote_items = []

        if remote_items:
            self._warm_catalog_cache(request, remote_items)

        merged = self._merge_items(cached_items, remote_items, limit=limit)
        if include_balance and source_site_id:
            merged = self._enrich_with_balances(request, merged, source_site_id)
        return _ok({"results": merged})

    def _search_local_cache(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        lookup = CatalogLookupService()
        items = lookup.search_items(query, limit=limit)
        return [
            {
                "id": str(item["id"]),
                "name": item.get("name", ""),
                "sku": item.get("sku", ""),
                "category_id": str(item.get("category_id", "")) if item.get("category_id") else "",
                "category_name": item.get("category_name", ""),
                "hashtags": item.get("hashtags", []),
                "unit_id": "",
                "unit_name": item.get("unit_symbol", ""),
                "unit_symbol": item.get("unit_symbol", ""),
                "is_active": item.get("is_active", True),
                "requires_review": False,
                "source": "cache",
                "source_site_id": "",
                "source_site_qty": "0",
                "balance_qty": "0",
            }
            for item in items
        ]

    def _search_remote_items(self, request, query: str, *, limit: int) -> list[dict[str, Any]]:
        client = _build_client(request)
        catalog = CatalogService(client)
        result = catalog.browse_items(search=query, page=1, page_size=max(limit, 25))
        if not result.ok:
            return []

        payload = result.data if isinstance(result.data, dict) else {}
        items = payload.get("items", []) if isinstance(payload, dict) else []

        serialized: list[dict[str, Any]] = []
        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue
            if not item.get("is_active", True):
                continue
            hashtags = item.get("hashtags")
            if not isinstance(hashtags, list):
                hashtags = []
            serialized.append({
                "id": str(item_id),
                "name": item.get("name", ""),
                "sku": item.get("sku", ""),
                "category_id": str(item.get("category_id", "")) if item.get("category_id") else "",
                "category_name": item.get("category_name", ""),
                "hashtags": hashtags,
                "unit_id": str(item.get("unit_id", "")) if item.get("unit_id") else "",
                "unit_name": item.get("unit_name", ""),
                "unit_symbol": item.get("unit_symbol", ""),
                "is_active": item.get("is_active", True),
                "requires_review": item.get("requires_review", False),
                "source": "remote",
                "source_site_id": "",
                "source_site_qty": "0",
                "balance_qty": "0",
            })
            if len(serialized) >= limit:
                break
        return serialized

    def _warm_catalog_cache(self, request, items: list[dict[str, Any]]) -> None:
        try:
            client = _build_client(request)
            sync_client = SyncServerClient(request=request, force_root=True)
            CatalogCacheSyncService(client=sync_client).upsert_items(items)
        except Exception:
            logger.error("catalog_cache_warm_failed", exc_info=True)

    def _enrich_with_balances(self, request, items: list[dict[str, Any]], source_site_id: str) -> list[dict[str, Any]]:
        if not source_site_id or not items:
            return items
        try:
            client = _build_client(request)
            balances_api = BalancesAPI(client=client)
            enriched: list[dict[str, Any]] = []
            for item in items:
                item_id = item.get("id", "")
                balance_qty = "0"
                if item_id:
                    try:
                        balance_data = balances_api.list_balances(
                            filters={"site_id": source_site_id, "item_id": item_id}
                        )
                        balance_items = balance_data.get("items", []) if isinstance(balance_data, dict) else []
                        if balance_items:
                            balance_qty = str(balance_items[0].get("qty", "0"))
                    except Exception:
                        logger.warning("balance_fetch_failed", item_id=item_id, exc_info=True)
                enriched.append({
                    **item,
                    "source_site_id": source_site_id,
                    "source_site_qty": balance_qty,
                    "balance_qty": balance_qty,
                })
            return enriched
        except Exception:
            logger.warning("Balance enrichment failed", exc_info=True)
            return items

    @staticmethod
    def _merge_items(
        cached: list[dict[str, Any]],
        remote: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in [*cached, *remote]:
            item_id = item.get("id", "")
            if not item_id or item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            merged.append(item)
            if len(merged) >= limit:
                break
        return merged


class CatalogCachedCategorySearchView(LoginRequiredMixin, View):
    """BFF endpoint for category search - BFF-mediated SyncServer (no local cache yet)."""

    def get(self, request):
        query = (request.GET.get("q") or "").strip()
        if len(query) < 1:
            return _ok({"results": []})

        try:
            limit = min(max(int(request.GET.get("limit") or 20), 1), 50)
        except (TypeError, ValueError):
            limit = 20

        try:
            client = _build_client(request)
            catalog = CatalogService(client)
            result = catalog.browse_categories(
                search=query,
                page=1,
                page_size=limit,
            )
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

        if not result.ok:
            return _ok({"results": []})

        payload = result.data if isinstance(result.data, dict) else {}
        categories = payload.get("categories", []) if isinstance(payload, dict) else []

        results: list[dict[str, Any]] = []
        for cat in categories:
            cat_id = cat.get("id")
            if not cat_id:
                continue
            if not cat.get("is_active", True):
                continue

            parent_id = cat.get("parent_id")
            path = cat.get("path", "")
            if not path and cat.get("parent_name"):
                path = f"{cat.get('parent_name')} / {cat.get('name', '')}"

            results.append({
                "id": str(cat_id),
                "name": cat.get("name", ""),
                "parent_id": str(parent_id) if parent_id else "",
                "path": path,
                "is_active": cat.get("is_active", True),
                "source": "remote",
            })
            if len(results) >= limit:
                break

        return _ok({"results": results})


# ── Admin Merge ─────────────────────────────────────────────────────


class AdminItemMergeView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body)
            api = CatalogAPI(_build_client(request))
            data = api.merge_items(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class AdminCategoryMergeView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body)
            api = CatalogAPI(_build_client(request))
            data = api.merge_categories(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
