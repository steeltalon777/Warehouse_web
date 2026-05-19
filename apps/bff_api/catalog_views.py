import json
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _extract_pagination,
    _handle_sync_error,
    _ok,
    _error,
    _require_chief_or_root,
)
from apps.sync_client.catalog_api import CatalogAPI
from apps.sync_client.exceptions import SyncServerAPIError


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
