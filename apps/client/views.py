from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render

from apps.catalog.services import CatalogService
from apps.client.forms import OperationCreateForm, SyncUserForm
from apps.client.services import DomainService
from apps.common.permissions import can_manage_catalog, is_storekeeper


domain_service = DomainService()
catalog_service = CatalogService()


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
def root_users(request):
    """
    Legacy users page retained only as a stub.

    Canonical Warehouse_web architecture no longer uses:
    - /users
    - /roles
    - /sites

    Admin management that exists today should go through:
    - admin_panel/sites
    - admin_panel/devices
    - admin_panel/access
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden("Нет доступа")

    messages.warning(
        request,
        "Управление пользователями через legacy SyncServer endpoints отключено. "
        "Используй страницы sites/devices/access в admin panel. "
        "Новый user API на стороне SyncServer пока не подключён.",
    )

    form = SyncUserForm(roles=[], sites=[])

    return render(
        request,
        "client/root_users.html",
        {
            "users": [],
            "roles": [],
            "sites": [],
            "form": form,
            "legacy_user_management_disabled": True,
        },
    )


@login_required
def root_user_create(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Нет доступа")

    messages.error(
        request,
        "Создание пользователей через legacy /users API отключено. "
        "Текущий SyncServer contract для Warehouse_web это не поддерживает.",
    )
    return redirect("client:root_users")


@login_required
def root_user_edit(request, user_id: str):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Нет доступа")

    messages.error(
        request,
        "Редактирование пользователей через legacy /users API отключено. "
        "Текущий SyncServer contract для Warehouse_web это не поддерживает.",
    )
    return redirect("client:root_users")


@login_required
def balances_view(request):
    if not (is_storekeeper(request.user) or can_manage_catalog(request.user) or request.user.is_superuser):
        return HttpResponseForbidden("Нет доступа")

    search = request.GET.get("search") or None
    result = domain_service.balances(search=search)
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
    result = domain_service.operations(search=search, limit=100)
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
            result = domain_service.create_operation(form.cleaned_data)
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

    search = request.GET.get("search") or None
    items_result = catalog_service.list_items(search=search)
    if not items_result.ok:
        messages.error(request, items_result.form_error)

    return render(
        request,
        "client/storekeeper_catalog.html",
        {
            "items": items_result.data or [],
            "search": search or "",
        },
    )