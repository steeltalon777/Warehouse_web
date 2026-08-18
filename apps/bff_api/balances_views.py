from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _extract_pagination,
    _handle_sync_error,
    _ok,
    _error,
)
from apps.sync_client.balances_api import BalancesAPI
from apps.sync_client.exceptions import SyncServerAPIError


def _balances(request):
    return BalancesAPI(_build_client(request))


class BalancesView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _balances(request)
            params = _extract_pagination(request)
            for key in ("site_id", "item_id", "item_ids", "category_id", "search", "only_positive"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_balances(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class BalancesBySiteView(LoginRequiredMixin, View):
    def get(self, request):
        site_id = request.GET.get("site_id")
        if not site_id:
            return _error("site_id is required", "validation_error", 400)
        try:
            api = _balances(request)
            only_positive = request.GET.get("only_positive", "false").lower() == "true"
            page = int(request.GET.get("page", 1))
            page_size = int(request.GET.get("page_size", 100))
            data = api.by_site(
                site_id=site_id,
                only_positive=only_positive,
                page=page,
                page_size=page_size,
            )
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class BalancesSummaryView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _balances(request)
            data = api.get_balances_summary()
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
