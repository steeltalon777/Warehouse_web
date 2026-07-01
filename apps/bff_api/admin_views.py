import json
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _extract_pagination,
    _handle_sync_error,
    _ok,
    _error,
    _require_root,
    _require_chief_or_root,
)
from apps.sync_client.exceptions import SyncServerAPIError


class RolesView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            data = client.get("/admin/roles")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class SitesListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            for key in ("is_active", "search", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = client.get("/admin/sites", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.post("/admin/sites", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class SiteDetailView(LoginRequiredMixin, View):
    def patch(self, request, site_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.patch(f"/admin/sites/{site_id}", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class UsersListView(LoginRequiredMixin, View):
    def get(self, request):
        if not _require_root(request.user):
            return _error("Only root can list users", "forbidden", 403)
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            for key in ("is_active", "is_root", "role", "search", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = client.get("/admin/users", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_root(request.user):
            return _error("Only root can create users", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.post("/admin/users", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class UserDetailView(LoginRequiredMixin, View):
    def get(self, request, user_id):
        if not _require_root(request.user):
            return _error("Only root can view users", "forbidden", 403)
        try:
            client = _build_client(request)
            data = client.get(f"/admin/users/{user_id}")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, user_id):
        if not _require_root(request.user):
            return _error("Only root can update users", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.patch(f"/admin/users/{user_id}", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

    def delete(self, request, user_id):
        if not _require_root(request.user):
            return _error("Only root can delete users", "forbidden", 403)
        try:
            client = _build_client(request)
            data = client.delete(f"/admin/users/{user_id}")
            return _ok(data if data else {"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class UserSyncStateView(LoginRequiredMixin, View):
    def get(self, request, user_id):
        if not _require_root(request.user):
            return _error("Only root can view sync state", "forbidden", 403)
        try:
            client = _build_client(request)
            data = client.get(f"/admin/users/{user_id}/sync-state")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class UserScopesView(LoginRequiredMixin, View):
    def put(self, request, user_id):
        if not _require_root(request.user):
            return _error("Only root can manage scopes", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.put(f"/admin/users/{user_id}/scopes", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class UserRotateTokenView(LoginRequiredMixin, View):
    def post(self, request, user_id):
        if not _require_root(request.user):
            return _error("Only root can rotate tokens", "forbidden", 403)
        try:
            client = _build_client(request)
            data = client.post(f"/admin/users/{user_id}/rotate-token", json={})
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class AccessScopesListView(LoginRequiredMixin, View):
    def get(self, request):
        if not _require_root(request.user):
            return _error("Only root can list access scopes", "forbidden", 403)
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            for key in ("user_id", "site_id", "is_active", "limit", "offset"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = client.get("/admin/access/scopes", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_root(request.user):
            return _error("Only root can create access scopes", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.post("/admin/access/scopes", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class AccessScopeDetailView(LoginRequiredMixin, View):
    def patch(self, request, scope_id):
        if not _require_root(request.user):
            return _error("Only root can update access scopes", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.patch(f"/admin/access/scopes/{scope_id}", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class DevicesListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            client = _build_client(request)
            params: dict[str, Any] = {}
            for key in ("site_id", "is_active", "search", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = client.get("/admin/devices", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.post("/admin/devices", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class DeviceDetailView(LoginRequiredMixin, View):
    def get(self, request, device_id):
        try:
            client = _build_client(request)
            data = client.get(f"/admin/devices/{device_id}")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, device_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            client = _build_client(request)
            payload = json.loads(request.body) if request.body else {}
            data = client.patch(f"/admin/devices/{device_id}", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

    def delete(self, request, device_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            client = _build_client(request)
            data = client.delete(f"/admin/devices/{device_id}")
            return _ok(data if data else {"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class DeviceRotateTokenView(LoginRequiredMixin, View):
    def post(self, request, device_id):
        if not _require_chief_or_root(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            client = _build_client(request)
            data = client.post(f"/admin/devices/{device_id}/rotate-token", json={})
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class DeviceSyncStatusView(LoginRequiredMixin, View):
    def get(self, request, device_id):
        if not _require_root(request.user):
            return _error("Only root can view device sync status", "forbidden", 403)
        try:
            from apps.users.services import DeviceSyncService
            data = DeviceSyncService().fetch_device_sync_status(int(device_id))
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except (ValueError, TypeError):
            return _error("Invalid device_id", "validation_error", 400)


class DeviceRefreshStatusView(LoginRequiredMixin, View):
    def post(self, request, device_id):
        if not _require_root(request.user):
            return _error("Only root can refresh device status", "forbidden", 403)
        try:
            from apps.users.models import SyncDeviceBinding
            from apps.users.services import DeviceSyncService
            binding = SyncDeviceBinding.objects.get(syncserver_device_id=int(device_id))
            service = DeviceSyncService()
            service.refresh_device_status(binding=binding)
            return _ok({
                "sync_state_status": binding.sync_state_status,
                "sync_state_last_seq": binding.sync_state_last_seq,
                "sync_state_behind_by": binding.sync_state_behind_by,
                "health_status": binding.health_status,
                "last_seen_at": binding.last_seen_at,
            })
        except SyncDeviceBinding.DoesNotExist:
            return _error("Device binding not found", "not_found", 404)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except (ValueError, TypeError):
            return _error("Invalid device_id", "validation_error", 400)
