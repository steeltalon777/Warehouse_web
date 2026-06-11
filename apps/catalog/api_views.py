from __future__ import annotations

import json
from typing import Any

import structlog
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin

from apps.sync_client.client import SyncServerClient
from apps.sync_client.catalog_api import CatalogAPI
from apps.sync_client.exceptions import SyncServerAPIError

logger = structlog.get_logger()


def _build_service(request):
    client = SyncServerClient(
        user_id=request.user.id,
        request=request,
    )
    return CatalogAPI(client)


def _ok(data: Any) -> JsonResponse:
    return JsonResponse({"ok": True, "data": data})


def _error(message: str, code: str = "error", status: int = 400) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": {"code": code, "message": message}},
        status=status,
    )


class BootstrapView(LoginRequiredMixin, View):
    """GET /nomenclature/api/bootstrap/ — load all catalogue data at once"""

    def get(self, request):
        try:
            api = _build_service(request)
            tree = api.get_categories_tree()
            items_result = api.browse_all_items()
            units_raw = api.list_units(filters={"limit": 500})
            return _ok({
                "categories_tree": tree if isinstance(tree, dict) else {"children": tree if isinstance(tree, list) else []},
                "items": items_result["items"],
                "items_total": items_result["total_count"],
                "items_loaded": items_result["loaded_count"],
                "items_complete": items_result["complete"],
                "units": units_raw if isinstance(units_raw, list) else [],
                "user": {
                    "id": str(request.user.id),
                    "username": request.user.username,
                },
                "permissions": list(request.user.get_group_permissions() or []),
            })
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)


class CategoryTreeView(LoginRequiredMixin, View):
    """GET /nomenclature/api/categories/ — return category tree"""

    def get(self, request):
        try:
            api = _build_service(request)
            tree = api.get_categories_tree()
            return _ok(tree)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)

    def post(self, request):
        """POST /nomenclature/api/categories/ — create category"""
        try:
            api = _build_service(request)
            body = json.loads(request.body)
            data = api.create_category(body)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)


class CategoryDetailView(LoginRequiredMixin, View):
    """GET/DELETE /nomenclature/api/categories/<id>/ — category detail or delete"""

    def get(self, request, pk):
        try:
            api = _build_service(request)
            data = api.get_category(str(pk))
            return _ok(data)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)

    def patch(self, request, pk):
        """PATCH /nomenclature/api/categories/<id>/ — update category"""
        try:
            api = _build_service(request)
            body = json.loads(request.body)
            data = api.update_category(str(pk), body)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)

    def delete(self, request, pk):
        try:
            api = _build_service(request)
            api.delete_category(str(pk))
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)


class ItemsListView(LoginRequiredMixin, View):
    """GET /nomenclature/api/items/ — items list with filters"""

    def get(self, request):
        try:
            filters: dict[str, Any] = {"limit": 1000}
            category_id = request.GET.get("category_id")
            search = request.GET.get("search")
            if category_id:
                filters["category_id"] = category_id
            if search:
                filters["search"] = search
            api = _build_service(request)
            items = api.list_items(filters=filters)
            if not isinstance(items, list):
                items = []
            return _ok({
                "items": items,
                "total": len(items),
            })
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)

    def post(self, request):
        """POST /nomenclature/api/items/ — create item"""
        try:
            api = _build_service(request)
            body = json.loads(request.body)
            data = api.create_item(body)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)


class ItemDetailView(LoginRequiredMixin, View):
    """GET/DELETE /nomenclature/api/items/<id>/ — item detail or delete"""

    def get(self, request, pk):
        try:
            api = _build_service(request)
            data = api.get_item(str(pk))
            return _ok(data)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)

    def patch(self, request, pk):
        """PATCH /nomenclature/api/items/<id>/ — update item"""
        try:
            api = _build_service(request)
            body = json.loads(request.body)
            data = api.update_item(str(pk), body)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)

    def delete(self, request, pk):
        try:
            api = _build_service(request)
            api.delete_item(str(pk))
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)


class UnitsListView(LoginRequiredMixin, View):
    """GET /nomenclature/api/units/ — units list"""

    def get(self, request):
        try:
            api = _build_service(request)
            units = api.list_units(filters={"limit": 500})
            return _ok(units if isinstance(units, list) else [])
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)

    def post(self, request):
        """POST /nomenclature/api/units/ — create unit"""
        try:
            api = _build_service(request)
            body = json.loads(request.body)
            data = api.create_unit(body)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)


class UnitDetailView(LoginRequiredMixin, View):
    """GET/PATCH/DELETE /nomenclature/api/units/<id>/ — unit detail, update or delete"""

    def get(self, request, pk):
        try:
            api = _build_service(request)
            data = api.get_unit(str(pk))
            return _ok(data)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)

    def patch(self, request, pk):
        """PATCH /nomenclature/api/units/<id>/ — update unit"""
        try:
            api = _build_service(request)
            body = json.loads(request.body)
            data = api.update_unit(str(pk), body)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)

    def delete(self, request, pk):
        try:
            api = _build_service(request)
            api.delete_unit(str(pk))
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _error(str(exc), "sync_error", status=exc.status_code or 502)
