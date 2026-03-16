from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import User
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.admin_panel.forms import DeviceForm, SiteForm, UserCreateForm
from apps.operations.views import SyncContextMixin
from apps.sync_client.admin_api import AdminAPI
from apps.sync_client.exceptions import SyncServerAPIError


class RootOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class UsersView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "admin_panel/users.html"

    def get(self, request, *args, **kwargs):
        users = []
        try:
            users = AdminAPI(self.client).users()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"users": users})


class UserCreateView(SyncContextMixin, RootOnlyMixin, View):
    template_name = "admin_panel/user_form.html"
    success_url = reverse_lazy("admin_panel:users")

    def _site_choices(self):
        sites = AdminAPI(self.client).sites()
        return [(str(site["id"]), site["name"]) for site in sites]

    def get(self, request):
        try:
            form = UserCreateForm(site_choices=self._site_choices())
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
            form = UserCreateForm(site_choices=[])
        return render(request, self.template_name, {"form": form, "mode": "create"})

    def post(self, request):
        try:
            site_choices = self._site_choices()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
            site_choices = []

        form = UserCreateForm(request.POST, site_choices=site_choices)

        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "mode": "create"})

        data = form.cleaned_data
        django_user = None

        try:
            django_user = User.objects.create_user(
                username=data["username"],
                password=data["password"],
                email=data.get("email") or "",
            )
            django_user.first_name = data.get("full_name") or ""
            django_user.is_active = data.get("is_active", True)
            django_user.save()

            AdminAPI(self.client).create_user(
                {
                    "user_id": str(django_user.id),
                    "username": data["username"],
                    "email": data.get("email") or "",
                    "full_name": data.get("full_name") or "",
                    "is_active": data.get("is_active", True),
                }
            )

            AdminAPI(self.client).create_user_site(
                {
                    "user_id": str(django_user.id),
                    "site_id": data["site_id"],
                    "role": data["role"],
                }
            )

            messages.success(request, "Пользователь создан.")
            return redirect(self.success_url)

        except SyncServerAPIError as exc:
            if django_user is not None:
                django_user.delete()
            form.add_error(None, str(exc))
            return render(request, self.template_name, {"form": form, "mode": "create"})

        except Exception as exc:
            if django_user is not None:
                django_user.delete()
            form.add_error(None, f"Ошибка создания пользователя: {exc}")
            return render(request, self.template_name, {"form": form, "mode": "create"})

class UserUpdateView(SyncContextMixin, RootOnlyMixin, View):
    template_name = "admin_panel/user_form.html"
    success_url = reverse_lazy("admin_panel:users")

    def _site_choices(self):
        sites = AdminAPI(self.client).sites()
        return [(str(site["id"]), site["name"]) for site in sites]

    def _find_sync_user(self, username: str):
        users = AdminAPI(self.client).users()
        for user in users:
            if str(user.get("username")) == str(username):
                return user
        return None

    def _find_user_access(self, username: str):
        access_rows = AdminAPI(self.client).user_sites()
        for row in access_rows:
            if str(row.get("username")) == str(username):
                return row
        return None

    def get(self, request, username: str):
        django_user = get_object_or_404(User, username=username)

        try:
            site_choices = self._site_choices()
            sync_user = self._find_sync_user(username)
            access = self._find_user_access(username)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
            return redirect(self.success_url)

        initial = {
            "username": django_user.username,
            "full_name": (sync_user or {}).get("full_name") or django_user.first_name,
            "email": django_user.email,
            "site_id": (access or {}).get("site_id"),
            "role": (access or {}).get("role"),
            "is_active": django_user.is_active,
        }

        form = UserCreateForm(site_choices=site_choices, initial=initial)
        form.fields["password"].required = False
        form.fields["password_confirm"].required = False

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "update",
                "edited_username": username,
            },
        )

    def post(self, request, username: str):
        django_user = get_object_or_404(User, username=username)

        try:
            site_choices = self._site_choices()
            old_access = self._find_user_access(username)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
            return redirect(self.success_url)

        form = UserCreateForm(request.POST, site_choices=site_choices)
        form.fields["password"].required = False
        form.fields["password_confirm"].required = False

        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "mode": "update",
                    "edited_username": username,
                },
            )

        data = form.cleaned_data

        try:
            old_username = django_user.username

            django_user.username = data["username"]
            django_user.email = data.get("email") or ""
            django_user.first_name = data.get("full_name") or ""
            django_user.is_active = data.get("is_active", True)

            if data.get("password"):
                django_user.set_password(data["password"])

            django_user.save()

            if old_access:
                AdminAPI(self.client).delete_user_site(
                    {
                        "user_id": str(old_access.get("user_id")),
                        "site_id": str(old_access.get("site_id")),
                    }
                )

            AdminAPI(self.client).create_user_site(
                {
                    "user_id": str(django_user.id),
                    "site_id": data["site_id"],
                    "role": data["role"],
                }
            )

            messages.success(request, "Пользователь обновлён.")
            return redirect(self.success_url)

        except SyncServerAPIError as exc:
            form.add_error(None, str(exc))
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "mode": "update",
                    "edited_username": username,
                },
            )

        except Exception as exc:
            form.add_error(None, f"Ошибка обновления пользователя: {exc}")
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "mode": "update",
                    "edited_username": username,
                },
            )



class UserToggleActiveView(SyncContextMixin, RootOnlyMixin, View):
    success_url = reverse_lazy("admin_panel:users")

    def get(self, request, username: str):
        django_user = get_object_or_404(User, username=username)
        django_user.is_active = not django_user.is_active
        django_user.save()

        state = "включён" if django_user.is_active else "отключён"
        messages.success(request, f"Пользователь {state}.")
        return redirect(self.success_url)


class SitesView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "admin_panel/sites.html"

    def get(self, request, *args, **kwargs):
        sites = []
        try:
            sites = AdminAPI(self.client).sites()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"sites": sites})


class SiteCreateView(SyncContextMixin, RootOnlyMixin, View):
    template_name = "admin_panel/site_form.html"
    success_url = reverse_lazy("admin_panel:sites")

    def get(self, request):
        return render(request, self.template_name, {"form": SiteForm(), "mode": "create"})

    def post(self, request):
        form = SiteForm(request.POST)
        if form.is_valid():
            try:
                AdminAPI(self.client).create_site(form.cleaned_data)
                messages.success(request, "Склад создан.")
                return redirect(self.success_url)
            except SyncServerAPIError as exc:
                form.add_error(None, str(exc))
        return render(request, self.template_name, {"form": form, "mode": "create"})


class SiteUpdateView(SyncContextMixin, RootOnlyMixin, View):
    template_name = "admin_panel/site_form.html"
    success_url = reverse_lazy("admin_panel:sites")

    def _find_site(self, site_id: str):
        for site in AdminAPI(self.client).sites():
            if str(site.get("id")) == str(site_id):
                return site
        return None

    def get(self, request, id):
        try:
            site = self._find_site(id)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
            site = None
        if site is None:
            raise Http404("Склад не найден")
        form = SiteForm(initial=site)
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def post(self, request, id):
        form = SiteForm(request.POST)
        if form.is_valid():
            try:
                AdminAPI(self.client).update_site(str(id), form.cleaned_data)
                messages.success(request, "Склад обновлён.")
                return redirect(self.success_url)
            except SyncServerAPIError as exc:
                if exc.status_code == 404:
                    raise Http404("Склад не найден")
                form.add_error(None, str(exc))
        return render(request, self.template_name, {"form": form, "mode": "update"})


class DevicesView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "admin_panel/devices.html"

    def get(self, request, *args, **kwargs):
        devices = []
        try:
            devices = AdminAPI(self.client).devices()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"devices": devices})


class DeviceCreateView(SyncContextMixin, RootOnlyMixin, View):
    template_name = "admin_panel/device_form.html"
    success_url = reverse_lazy("admin_panel:devices")

    def get(self, request):
        return render(request, self.template_name, {"form": DeviceForm(), "mode": "create"})

    def post(self, request):
        form = DeviceForm(request.POST)
        if form.is_valid():
            try:
                AdminAPI(self.client).create_device(form.cleaned_data)
                messages.success(request, "Устройство создано.")
                return redirect(self.success_url)
            except SyncServerAPIError as exc:
                form.add_error(None, str(exc))
        return render(request, self.template_name, {"form": form, "mode": "create"})


class DeviceUpdateView(SyncContextMixin, RootOnlyMixin, View):
    template_name = "admin_panel/device_form.html"
    success_url = reverse_lazy("admin_panel:devices")

    def _find_device(self, device_id: str):
        for device in AdminAPI(self.client).devices():
            if str(device.get("id")) == str(device_id):
                return device
        return None

    def get(self, request, id):
        try:
            device = self._find_device(id)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
            device = None
        if device is None:
            raise Http404("Устройство не найдено")
        form = DeviceForm(initial=device)
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def post(self, request, id):
        form = DeviceForm(request.POST)
        if form.is_valid():
            try:
                AdminAPI(self.client).update_device(str(id), form.cleaned_data)
                messages.success(request, "Устройство обновлено.")
                return redirect(self.success_url)
            except SyncServerAPIError as exc:
                if exc.status_code == 404:
                    raise Http404("Устройство не найдено")
                form.add_error(None, str(exc))
        return render(request, self.template_name, {"form": form, "mode": "update"})


class AccessView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "admin_panel/access.html"

    def get(self, request, *args, **kwargs):
        access = []
        try:
            access = AdminAPI(self.client).user_sites()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"access": access})