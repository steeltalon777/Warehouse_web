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
from apps.sync_client.assets_api import AssetsAPI
from apps.sync_client.exceptions import SyncServerAPIError


def _assets(request):
    return AssetsAPI(_build_client(request))


class PendingAcceptanceView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _assets(request)
            params: dict[str, str] = {}
            for key in ("site_id", "operation_id", "item_id", "search", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_pending_acceptance(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class LostAssetsListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _assets(request)
            params: dict[str, str] = {}
            for key in ("site_id", "source_site_id", "operation_id", "item_id",
                        "search", "updated_after", "updated_before",
                        "qty_from", "qty_to", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_lost_assets(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class LostAssetDetailView(LoginRequiredMixin, View):
    def get(self, request, operation_line_id):
        try:
            api = _assets(request)
            data = api.get_lost_asset(operation_line_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class LostAssetResolveView(LoginRequiredMixin, View):
    def post(self, request, operation_line_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _assets(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.resolve_lost_asset(operation_line_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class IssuedAssetsView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _assets(request)
            params: dict[str, str] = {}
            for key in ("issue_object_id", "item_id", "search", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_issued_assets(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
