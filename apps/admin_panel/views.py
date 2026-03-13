from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import render
from django.views.generic import TemplateView

from apps.operations.views import SyncContextMixin
from apps.sync_client.admin_api import AdminAPI
from apps.sync_client.exceptions import SyncServerAPIError


class RootOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class UsersView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "client/root_users.html"

    def get(self, request, *args, **kwargs):
        # legacy users page retained while users endpoint migration is pending
        return render(request, self.template_name, {"users": []})


class SitesView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "admin_panel/sites.html"

    def get(self, request, *args, **kwargs):
        sites = []
        try:
            sites = AdminAPI(self.client).sites()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"sites": sites})


class DevicesView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "admin_panel/devices.html"

    def get(self, request, *args, **kwargs):
        devices = []
        try:
            devices = AdminAPI(self.client).devices()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"devices": devices})


class AccessView(SyncContextMixin, RootOnlyMixin, TemplateView):
    template_name = "admin_panel/access.html"

    def get(self, request, *args, **kwargs):
        access = []
        try:
            access = AdminAPI(self.client).user_sites()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc))
        return render(request, self.template_name, {"access": access})
