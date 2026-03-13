from django.contrib import messages
from django.shortcuts import render
from django.views.generic import TemplateView

from apps.operations.views import SyncContextMixin
from apps.sync_client.balances_api import BalancesAPI
from apps.sync_client.exceptions import SyncServerAPIError


class BalancesListView(SyncContextMixin, TemplateView):
    template_name = "client/balances.html"

    def get(self, request, *args, **kwargs):
        limit = int(request.GET.get("limit", 20))
        offset = int(request.GET.get("offset", 0))
        search = request.GET.get("search") or None
        balances = []
        summary = {}
        api = BalancesAPI(self.client)
        try:
            balances = api.list(limit=limit, offset=offset, search=search)
            summary = api.summary()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))

        return render(
            request,
            self.template_name,
            {
                "balances": balances,
                "summary": summary,
                "search": search or "",
                "limit": limit,
                "offset": offset,
                "prev_offset": max(offset - limit, 0),
                "next_offset": offset + limit,
            },
        )


class BalancesBySiteView(SyncContextMixin, TemplateView):
    template_name = "balances/by_site.html"

    def get(self, request, *args, **kwargs):
        limit = int(request.GET.get("limit", 20))
        offset = int(request.GET.get("offset", 0))
        records = []
        try:
            records = BalancesAPI(self.client).by_site(limit=limit, offset=offset)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"records": records, "limit": limit, "offset": offset})
