import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from apps.bff_api.helpers import _build_client, _handle_sync_error, _ok, _error, _require_root
from apps.sync_client.exceptions import SyncServerAPIError


class SyncUserView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_root(request.user):
            return _error("Only root can sync users", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.post("/auth/sync-user", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class MeView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            data = client.get("/auth/me")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class SitesView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            data = client.get("/auth/sites")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class ContextView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            data = client.get("/auth/context")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
