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
    if not request.user.is_superuser:
        return HttpResponseForbidden("Нет доступа")

    users_result = domain_service.users()
    roles_result = domain_service.roles()
    sites_result = domain_service.sites()
    if not users_result.ok:
        messages.error(request, users_result.form_error)
    if not roles_result.ok:
        messages.error(request, roles_result.form_error)
    if not sites_result.ok:
        messages.error(request, sites_result.form_error)

    form = SyncUserForm(roles=roles_result.data or [], sites=sites_result.data or [])

    return render(
        request,
        "client/root_users.html",
        {
            "users": users_result.data or [],
            "roles": roles_result.data or [],
            "sites": sites_result.data or [],
            "form": form,
        },
    )


@login_required
def root_user_create(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Нет доступа")

    roles = (domain_service.roles().data or [])
    sites = (domain_service.sites().data or [])

    if request.method == "POST":
        form = SyncUserForm(request.POST, roles=roles, sites=sites)
        if form.is_valid():
            payload = form.cleaned_data
            if not payload.get("password"):
                payload.pop("password", None)
            result = domain_service.create_user(payload)
            if result.ok:
                messages.success(request, "Пользователь создан в SyncServer.")
                return redirect("client:root_users")
            form.add_error(None, result.form_error)
    else:
        form = SyncUserForm(roles=roles, sites=sites)

    return render(request, "client/root_user_form.html", {"form": form, "mode": "create"})


@login_required
def root_user_edit(request, user_id: str):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Нет доступа")

    users_result = domain_service.users()
    user_data = next((x for x in (users_result.data or []) if str(x.get("id")) == str(user_id)), None)
    if user_data is None:
        raise Http404("Пользователь не найден")

    roles = (domain_service.roles().data or [])
    sites = (domain_service.sites().data or [])

    if request.method == "POST":
        form = SyncUserForm(request.POST, roles=roles, sites=sites)
        if form.is_valid():
            payload = form.cleaned_data
            if not payload.get("password"):
                payload.pop("password", None)
            result = domain_service.update_user(user_id, payload)
            if result.ok:
                messages.success(request, "Пользователь обновлён в SyncServer.")
                return redirect("client:root_users")
            form.add_error(None, result.form_error)
    else:
        form = SyncUserForm(initial=user_data, roles=roles, sites=sites)

    return render(request, "client/root_user_form.html", {"form": form, "mode": "edit", "user_id": user_id})


@login_required
def balances_view(request):
    if not (is_storekeeper(request.user) or can_manage_catalog(request.user) or request.user.is_superuser):
        return HttpResponseForbidden("Нет доступа")

    search = request.GET.get("search") or None
    result = domain_service.balances(search=search)
    if not result.ok:
        messages.error(request, result.form_error)
    return render(request, "client/balances.html", {"balances": result.data or [], "search": search or ""})


@login_required
def operations_view(request):
    if not (is_storekeeper(request.user) or can_manage_catalog(request.user) or request.user.is_superuser):
        return HttpResponseForbidden("Нет доступа")

    search = request.GET.get("search") or None
    result = domain_service.operations(search=search, limit=100)
    if not result.ok:
        messages.error(request, result.form_error)

    return render(request, "client/operations.html", {"operations": result.data or [], "search": search or ""})


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
