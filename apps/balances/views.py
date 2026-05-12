from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.shortcuts import render
from django.views.generic import TemplateView

from apps.catalog.services import CatalogService
from apps.common.permissions import get_user_role
from apps.common.api_error_handler import handle_api_errors, log_api_call
from apps.common.mixins import SyncContextMixin
from apps.sync_client.balances_api import BalancesAPI
from apps.sync_client.client import SyncServerClient


def _parse_positive_int(raw_value: str | None, default: int) -> int:
    try:
        value = int(raw_value or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _get_sites_index(client) -> dict[int, dict[str, Any]]:
    try:
        root_client = SyncServerClient(request=getattr(client, "request", None), force_root=True)
        response = root_client.get("/catalog/sites")
        sites = response.get("sites", []) if isinstance(response, dict) else []
    except Exception:
        response = client.get("/auth/sites")
        sites = response.get("available_sites", []) if isinstance(response, dict) else []
    sites_index: dict[int, dict[str, Any]] = {}
    for site in sites:
        try:
            site_id = int(site.get("site_id"))
        except (TypeError, ValueError):
            continue
        sites_index[site_id] = {
            "site_id": site_id,
            "name": str(site.get("name") or site.get("code") or site_id),
        }
    return sites_index


def _get_sites_list(client) -> list[dict[str, Any]]:
    return sorted(_get_sites_index(client).values(), key=lambda site: site["name"])


def _get_items_index(client) -> dict[int, dict[str, Any]]:
    result = CatalogService(client).list_items()
    if not result.ok:
        return {}

    items_index: dict[int, dict[str, Any]] = {}
    for item in result.data or []:
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        items_index[item_id] = {
            "id": item_id,
            "name": str(item.get("name") or item.get("sku") or item_id),
            "sku": str(item.get("sku") or ""),
        }
    return items_index


def _get_user_default_site_id(request) -> str:
    default_site_id = (
        request.session.get("sync_default_site_id")
        or request.session.get("active_site")
        or request.session.get("site_id")
        or getattr(getattr(request.user, "sync_binding", None), "default_site_id", "")
    )
    return str(default_site_id or "")


def _get_default_balance_site_id(request) -> str:
    return ""


def _present_balance_row(
    row: dict[str, Any],
    *,
    sites_index: dict[int, dict[str, Any]],
    items_index: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    quantity = row.get("qty")
    if quantity is None:
        quantity = row.get("quantity")
    if quantity is None:
        quantity = 0

    try:
        quantity_value = float(quantity)
    except (TypeError, ValueError):
        quantity_value = 0.0

    site_id = row.get("site_id")
    try:
        normalized_site_id = int(site_id) if site_id is not None else None
    except (TypeError, ValueError):
        normalized_site_id = None
    site = sites_index.get(normalized_site_id) if normalized_site_id is not None else None

    item_id = row.get("item_id")
    try:
        normalized_item_id = int(item_id) if item_id is not None else None
    except (TypeError, ValueError):
        normalized_item_id = None
    item = items_index.get(normalized_item_id) if normalized_item_id is not None else None
    item_name = row.get("display_name") or row.get("item_name")
    sku = row.get("sku") or (item.get("sku") if item else "")
    category_name = row.get("category_name") or ""

    if quantity_value <= 0:
        status_label = "Не в наличии"
        status_tone = "danger"
    elif quantity_value < 10:
        status_label = "Низкий запас"
        status_tone = "warning"
    else:
        status_label = "В наличии"
        status_tone = "success"

    return {
        "item_id": item_id,
        "item_name": str(item_name or (item.get("name") if item else "") or item_id),
        "sku": str(sku or ""),
        "category_name": str(category_name or ""),
        "site_id": site_id,
        "site_name": str(site.get("name") or site_id) if site else site_id,
        "quantity": quantity,
        "updated_at": row.get("updated_at"),
        "status_label": status_label,
        "status_tone": status_tone,
    }


class BalancesListView(SyncContextMixin, TemplateView):
    template_name = "balances/list.html"

    @handle_api_errors(operation="Получение списка остатков")
    def get(self, request, *args, **kwargs):
        page = _parse_positive_int(request.GET.get("page"), 1)
        page_size = _parse_positive_int(request.GET.get("page_size"), 20)
        search = request.GET.get("search") or None
        item_id = request.GET.get("item_id") or None
        raw_site_id = request.GET.get("site_id") if "site_id" in request.GET else _get_default_balance_site_id(request)
        site_id = raw_site_id or None
        only_positive = request.GET.get("only_positive") == "1"

        filters: dict[str, Any] = {
            "search": search,
            "item_id": item_id,
            "site_id": site_id,
            "only_positive": only_positive,
        }

        log_api_call(
            method="GET",
            path="/balances",
            context={
                "filters": {k: v for k, v in filters.items() if v not in (None, "", False)},
                "page": page,
                "page_size": page_size,
            },
        )

        response = BalancesAPI(self.client).list_balances(
            filters=filters,
            page=page,
            page_size=page_size,
        )
        sites_index = _get_sites_index(self.client)
        sites = sorted(sites_index.values(), key=lambda site: site["name"])
        items_index = _get_items_index(self.client)
        balances = [
            _present_balance_row(row, sites_index=sites_index, items_index=items_index)
            for row in response.get("items", [])
        ]
        total_count = int(response.get("total_count", len(balances)) or 0)
        has_previous = page > 1
        has_next = page * page_size < total_count

        return render(
            request,
            self.template_name,
            {
                "balances": balances,
                "search": search or "",
                "item_id": item_id or "",
                "site_id": raw_site_id or "",
                "sites": sites,
                "only_positive": only_positive,
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "prev_page": page - 1,
                "next_page": page + 1,
                "has_previous": has_previous,
                "has_next": has_next,
            },
        )


class BalancesSummaryView(SyncContextMixin, TemplateView):
    template_name = "balances/summary.html"

    @handle_api_errors(operation="Получение сводки по остаткам")
    def get(self, request, *args, **kwargs):
        log_api_call(method="GET", path="/balances/summary")
        response = BalancesAPI(self.client).get_balances_summary()
        summary = response.get("summary", {}) if isinstance(response, dict) else {}
        accessible_sites_count = (
            int(response.get("accessible_sites_count", 0) or 0)
            if isinstance(response, dict)
            else 0
        )

        return render(
            request,
            self.template_name,
            {
                "summary": summary,
                "accessible_sites_count": accessible_sites_count,
            },
        )


class BalancesBySiteView(SyncContextMixin, TemplateView):
    template_name = "balances/by_site.html"

    @handle_api_errors(operation="Получение остатков по складу")
    def get(self, request, *args, **kwargs):
        page = _parse_positive_int(request.GET.get("page"), 1)
        page_size = _parse_positive_int(request.GET.get("page_size"), 20)
        site_id = request.GET.get("site_id") or ""
        only_positive = request.GET.get("only_positive") == "1"

        if not site_id:
            messages.info(request, "Укажите склад, чтобы посмотреть остатки по нему.")
            return render(
                request,
                self.template_name,
                {
                    "records": [],
                    "site_id": "",
                    "sites": _get_sites_list(self.client),
                    "only_positive": only_positive,
                    "page": page,
                    "page_size": page_size,
                    "has_previous": False,
                    "has_next": False,
                    "prev_page": 1,
                    "next_page": 2,
                    "total_count": 0,
                },
            )

        log_api_call(
            method="GET",
            path="/balances/by-site",
            context={
                "site_id": site_id,
                "only_positive": only_positive,
                "page": page,
                "page_size": page_size,
            },
        )

        response = BalancesAPI(self.client).by_site(
            site_id=site_id,
            only_positive=only_positive,
            page=page,
            page_size=page_size,
        )
        sites_index = _get_sites_index(self.client)
        sites = sorted(sites_index.values(), key=lambda site: site["name"])
        items_index = _get_items_index(self.client)
        records = [
            _present_balance_row(row, sites_index=sites_index, items_index=items_index)
            for row in response.get("items", [])
        ]
        total_count = int(response.get("total_count", len(records)) or 0)

        return render(
            request,
            self.template_name,
            {
                "records": records,
                "site_id": site_id,
                "sites": sites,
                "only_positive": only_positive,
                "page": page,
                "page_size": page_size,
                "has_previous": page > 1,
                "has_next": page * page_size < total_count,
                "prev_page": page - 1,
                "next_page": page + 1,
                "total_count": total_count,
            },
        )
