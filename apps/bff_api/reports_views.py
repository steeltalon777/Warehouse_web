from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _handle_sync_error,
    _ok,
    _error,
)
from apps.sync_client.exceptions import SyncServerAPIError


class ItemMovementView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            params: dict[str, str] = {}
            for key in ("site_id", "item_id", "category_id", "search",
                        "date_from", "date_to", "page", "page_size",
                        "exclude_system_effects"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = client.get("/reports/item-movement", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class StockSummaryView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            params: dict[str, str] = {}
            for key in ("site_id", "category_id", "search", "only_positive", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = client.get("/reports/stock-summary", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
