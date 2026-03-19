from django.contrib import messages
from django.shortcuts import render
from django.views.generic import TemplateView

from apps.common.mixins import SyncContextMixin
from apps.sync_client.balances_api import BalancesAPI
from apps.sync_client.exceptions import SyncServerAPIError

from apps.common.api_error_handler import (
    APIErrorHandler,
    handle_api_errors,
    safe_api_call,
    log_api_call,
)


class BalancesListView(SyncContextMixin, TemplateView):
    template_name = "balances/list.html"

    @handle_api_errors(operation="Получение списка остатков")
    def get(self, request, *args, **kwargs):
        limit = int(request.GET.get("limit", 20))
        offset = int(request.GET.get("offset", 0))
        search = request.GET.get("search") or None
        item_id = request.GET.get("item_id") or None
        min_quantity = request.GET.get("min_quantity")
        max_quantity = request.GET.get("max_quantity")
        balances = []
        api = BalancesAPI(self.client)

        try:
            # Build filters
            filters = {}
            if search:
                filters["search"] = search
            if item_id:
                filters["item_id"] = item_id
            if min_quantity:
                try:
                    filters["min_quantity"] = float(min_quantity)
                except ValueError:
                    messages.warning(
                        request, "Некорректное значение минимального количества"
                    )
            if max_quantity:
                try:
                    filters["max_quantity"] = float(max_quantity)
                except ValueError:
                    messages.warning(
                        request, "Некорректное значение максимального количества"
                    )

            # Log API call
            log_api_call(
                method="GET",
                path="/balances",
                context={"filters": filters, "limit": limit, "offset": offset},
            )

            balances = api.list_balances(filters=filters)

        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "получении списка остатков"
            )

        return render(
            request,
            self.template_name,
            {
                "balances": balances,
                "search": search or "",
                "item_id": item_id or "",
                "min_quantity": min_quantity or "",
                "max_quantity": max_quantity or "",
                "limit": limit,
                "offset": offset,
                "prev_offset": max(offset - limit, 0),
                "next_offset": offset + limit,
            },
        )


class BalancesSummaryView(SyncContextMixin, TemplateView):
    template_name = "balances/summary.html"

    @handle_api_errors(operation="Получение сводки по остаткам")
    def get(self, request, *args, **kwargs):
        site_id = request.GET.get("site_id") or None

        summary = {}
        api = BalancesAPI(self.client)

        try:
            # Build filters
            filters = {}
            if site_id:
                filters["site_id"] = site_id

            # Log API call
            log_api_call(
                method="GET", path="/balances/summary", context={"filters": filters}
            )

            summary = api.get_balances_summary(filters=filters)

        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "получении сводки по остаткам"
            )

        return render(
            request,
            self.template_name,
            {
                "summary": summary,
                "site_id": site_id or "",
            },
        )


class BalancesBySiteView(SyncContextMixin, TemplateView):
    template_name = "balances/by_site.html"

    @handle_api_errors(operation="Получение остатков по складам")
    def get(self, request, *args, **kwargs):
        limit = int(request.GET.get("limit", 20))
        offset = int(request.GET.get("offset", 0))
        records = []

        try:
            # Log API call
            log_api_call(
                method="GET",
                path="/balances/by-site",
                context={"limit": limit, "offset": offset},
            )

            records = BalancesAPI(self.client).by_site(limit=limit, offset=offset)

        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "получении остатков по складам"
            )

        return render(
            request,
            self.template_name,
            {
                "records": records,
                "limit": limit,
                "offset": offset,
                "prev_offset": max(offset - limit, 0),
                "next_offset": offset + limit,
            },
        )


# Alternative implementation using safe_api_call
class SimpleBalancesListView(SyncContextMixin, TemplateView):
    """
    Alternative implementation using safe_api_call helper.
    Shows different approach to error handling.
    """

    template_name = "balances/list.html"

    def get(self, request, *args, **kwargs):
        limit = int(request.GET.get("limit", 20))
        offset = int(request.GET.get("offset", 0))
        search = request.GET.get("search") or None
        item_id = request.GET.get("item_id") or None
        min_quantity = request.GET.get("min_quantity")
        max_quantity = request.GET.get("max_quantity")

        api = BalancesAPI(self.client)

        # Build filters
        filters = {}
        if search:
            filters["search"] = search
        if item_id:
            filters["item_id"] = item_id
        if min_quantity:
            try:
                filters["min_quantity"] = float(min_quantity)
            except ValueError:
                messages.warning(
                    request, "Некорректное значение минимального количества"
                )
        if max_quantity:
            try:
                filters["max_quantity"] = float(max_quantity)
            except ValueError:
                messages.warning(
                    request, "Некорректное значение максимального количества"
                )

        # Use safe_api_call for error handling
        balances = (
            safe_api_call(
                api.list_balances,
                request,
                operation="Получение списка остатков",
                filters=filters,
            )
            or []
        )

        return render(
            request,
            self.template_name,
            {
                "balances": balances,
                "search": search or "",
                "item_id": item_id or "",
                "min_quantity": min_quantity or "",
                "max_quantity": max_quantity or "",
                "limit": limit,
                "offset": offset,
                "prev_offset": max(offset - limit, 0),
                "next_offset": offset + limit,
            },
        )
