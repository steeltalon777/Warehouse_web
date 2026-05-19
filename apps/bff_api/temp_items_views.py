import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _handle_sync_error,
    _ok,
    _error,
    _require_chief_or_root,
)
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.temporary_items_api import TemporaryItemsAPI


def _temp(request):
    return TemporaryItemsAPI(_build_client(request))


class TempItemsListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _temp(request)
            params: dict[str, str] = {}
            for key in (
                "status", "search", "created_by_user_id",
                "resolved_item_id", "created_after", "created_before",
                "page", "page_size",
            ):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_temporary_items_page(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class TempItemDetailView(LoginRequiredMixin, View):
    def get(self, request, temp_item_id):
        try:
            api = _temp(request)
            data = api.get_temporary_item(temp_item_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def delete(self, request, temp_item_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _temp(request)
            data = api.delete_temporary_item(temp_item_id)
            return _ok(data if data else {"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class TempItemOperationsView(LoginRequiredMixin, View):
    def get(self, request, temp_item_id):
        try:
            api = _temp(request)
            params: dict[str, str] = {}
            for key in ("page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_temporary_item_operations(temp_item_id, filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class TempItemApproveView(LoginRequiredMixin, View):
    def post(self, request, temp_item_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _temp(request)
            body = {}
            if request.body:
                body = json.loads(request.body)
            # Note: SyncServer approve_as_item currently ignores body.
            # Option B: convert with system defaults, user edits in nomenclature afterward.
            # Future: send body params when SyncServer supports them.
            data = api.approve_as_item(temp_item_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class TempItemMergeView(LoginRequiredMixin, View):
    def post(self, request, temp_item_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _temp(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.merge_to_item(temp_item_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)
