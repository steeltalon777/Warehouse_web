from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from apps.client.forms import OperationCreateForm
from apps.common.permissions import can_use_client
from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.operations_api import OperationsAPI


class SyncContextMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user):
            return self.handle_no_permission()
        self.site_id = (
                request.session.get("active_site")
                or getattr(getattr(request.user, "profile", None), "site_id", None)
        )
        self.client = SyncServerClient(user_id=request.user.id, site_id=self.site_id)
        return super().dispatch(request, *args, **kwargs)


class OperationsListView(SyncContextMixin, TemplateView):
    template_name = "client/operations.html"

    def get(self, request, *args, **kwargs):
        limit = int(request.GET.get("limit", 20))
        offset = int(request.GET.get("offset", 0))
        search = request.GET.get("search") or None
        api = OperationsAPI(self.client)
        operations = []
        try:
            operations = api.list(limit=limit, offset=offset, search=search)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))

        context = {
            "operations": operations,
            "search": search or "",
            "limit": limit,
            "offset": offset,
            "prev_offset": max(offset - limit, 0),
            "next_offset": offset + limit,
        }
        return render(request, self.template_name, context)


class OperationCreateView(SyncContextMixin, View):
    template_name = "client/operation_form.html"

    def get(self, request):
        return render(request, self.template_name, {"form": OperationCreateForm()})

    def post(self, request):
        form = OperationCreateForm(request.POST)
        if form.is_valid():
            try:
                created = OperationsAPI(self.client).create(form.cleaned_data)
                messages.success(request, "Операция создана.")
                return redirect("operations:detail", operation_id=created.get("id"))
            except SyncServerAPIError as exc:
                form.add_error(None, str(exc))
        return render(request, self.template_name, {"form": form})


class OperationDetailView(SyncContextMixin, TemplateView):
    template_name = "operations/detail.html"

    def get(self, request, operation_id):
        operation = None
        try:
            operation = OperationsAPI(self.client).get(operation_id)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"operation": operation})
