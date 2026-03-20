from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from apps.client.forms import OperationCreateForm
from apps.client.services import DomainService
from apps.common.permissions import can_manage_catalog, is_storekeeper
from apps.sync_client.client import SyncServerClient


def _build_domain_service(request) -> DomainService:
    site_id = (
        request.session.get("active_site")
        or request.session.get("sync_default_site_id")
        or request.session.get("site_id")
        or getattr(settings, "SYNC_DEFAULT_ACTING_SITE_ID", "")
    )
    client = SyncServerClient(
        user_id=request.user.id,
        site_id=site_id,
        request=request,
    )
    return DomainService(client)


@login_required
def dashboard(request):
    role = "storekeeper"
    if request.user.is_superuser:
        role = "root"
    elif can_manage_catalog(request.user):
        role = "chief_storekeeper"
    elif not is_storekeeper(request.user):
        return HttpResponseForbidden("Нет доступа")

    return render(request, "client/dashboard.html", {"role": role})


@login_required
def balances_view(request):
    if not (is_storekeeper(request.user) or can_manage_catalog(request.user) or request.user.is_superuser):
        return HttpResponseForbidden("Нет доступа")

    search = request.GET.get("search") or None
    result = _build_domain_service(request).balances(search=search)
    if not result.ok:
        messages.error(request, result.form_error)

    return render(
        request,
        "client/balances.html",
        {
            "balances": result.data or [],
            "search": search or "",
            "sync_error_type": (
                "backend_unavailable" if result.backend_unavailable else
                "auth_error" if result.auth_error else
                "forbidden" if result.forbidden else
                "not_found" if result.not_found else
                "validation_error" if result.validation_error else
                "conflict" if result.conflict else
                ""
            ),
        },
    )


@login_required
def operations_view(request):
    if not (is_storekeeper(request.user) or can_manage_catalog(request.user) or request.user.is_superuser):
        return HttpResponseForbidden("Нет доступа")

    search = request.GET.get("search") or None
    result = _build_domain_service(request).operations(search=search, limit=100)
    if not result.ok:
        messages.error(request, result.form_error)

    return render(
        request,
        "client/operations.html",
        {
            "operations": result.data or [],
            "search": search or "",
            "sync_error_type": (
                "backend_unavailable" if result.backend_unavailable else
                "auth_error" if result.auth_error else
                "forbidden" if result.forbidden else
                "not_found" if result.not_found else
                "validation_error" if result.validation_error else
                "conflict" if result.conflict else
                ""
            ),
        },
    )


@login_required
def operation_create(request):
    if not (is_storekeeper(request.user) or can_manage_catalog(request.user) or request.user.is_superuser):
        return HttpResponseForbidden("Нет доступа")

    if request.method == "POST":
        form = OperationCreateForm(request.POST)
        if form.is_valid():
            result = _build_domain_service(request).create_operation(form.cleaned_data)
            if result.ok:
                messages.success(request, "Операция отправлена в SyncServer.")
                return redirect("client:operations")
            form.add_error(None, result.form_error)
    else:
        form = OperationCreateForm()

    return render(request, "client/operation_form.html", {"form": form})


@login_required
def storekeeper_catalog(request):
    if not (is_storekeeper(request.user) or can_manage_catalog(request.user) or request.user.is_superuser):
        return HttpResponseForbidden("Нет доступа")
    return redirect("catalog:item_list")
