from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.common.mixins import SyncContextMixin
from apps.sync_client.admin_api import AdminAPI
from apps.sync_client.exceptions import SyncServerAPIError
from apps.users.models import SyncDeviceBinding


class RootOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class DevicesView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "admin_panel/devices.html"

    def get(self, request, *args, **kwargs):
        return redirect("admin:users_syncdevicebinding_changelist")


class DeviceCreateView(SyncContextMixin, RootOnlyMixin, View):
    def get(self, request):
        return redirect("admin:users_syncdevicebinding_add")

    def post(self, request):
        return redirect("admin:users_syncdevicebinding_add")


class DeviceUpdateView(SyncContextMixin, RootOnlyMixin, View):
    def _get_admin_change_url(self, device_id: str) -> str:
        binding = SyncDeviceBinding.objects.filter(syncserver_device_id=device_id).first()
        if binding is None:
            return reverse("admin:users_syncdevicebinding_changelist")
        return reverse("admin:users_syncdevicebinding_change", args=[binding.pk])

    def get(self, request, id):
        binding = SyncDeviceBinding.objects.filter(syncserver_device_id=id).first()
        if binding is None:
            messages.warning(request, "Устройство перенесено в Django admin. Локальная карточка не найдена.")
        return redirect(self._get_admin_change_url(id))

    def post(self, request, id):
        binding = SyncDeviceBinding.objects.filter(syncserver_device_id=id).first()
        if binding is None:
            messages.warning(request, "Устройство перенесено в Django admin. Локальная карточка не найдена.")
        return redirect(self._get_admin_change_url(id))


class AccessView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "admin_panel/access.html"

    def get(self, request, *args, **kwargs):
        access = []
        try:
            access = AdminAPI(self.client).user_sites()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"access": access})
