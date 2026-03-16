from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.admin_panel.forms import DeviceForm, SiteForm
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

class UserCreateView(SyncContextMixin, RootOnlyMixin, View):
    template_name = "admin_panel/user_form.html"
    success_url = reverse_lazy("admin_panel:users")

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        data = {
            "username": request.POST.get("username"),
            "email": request.POST.get("email"),
            "full_name": request.POST.get("full_name"),
        }

        try:
            AdminAPI(self.client).create_user(data)
            messages.success(request, "Пользователь создан.")
            return redirect(self.success_url)

        except SyncServerAPIError as exc:
            messages.error(request, str(exc))

        return render(request, self.template_name, {"data": data})