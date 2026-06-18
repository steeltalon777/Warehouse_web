from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, JsonResponse
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _error,
    _extract_pagination,
    _handle_sync_error,
    _ok,
    _require_root,
)
from apps.sync_client.exceptions import SyncServerAPIError
from apps.common.permissions import can_manage_catalog


def _require_audit_access(user) -> bool:
    """Audit requires root or chief_storekeeper level access."""
    return _require_root(user) or can_manage_catalog(user)


class AuditEventsListView(LoginRequiredMixin, View):
    """GET /bff/api/v1/admin/audit — list audit events with filters."""

    def get(self, request: HttpRequest) -> JsonResponse:
        if not _require_audit_access(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            client = _build_client(request)
            params = _extract_pagination(request)

            # Forward optional filter params
            for key in (
                "event_type",
                "actor_user_id",
                "site_id",
                "entity_type",
                "entity_id",
                "date_from",
                "date_to",
            ):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val

            data = client.get("/admin/audit", params=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class AuditEventDetailView(LoginRequiredMixin, View):
    """GET /bff/api/v1/admin/audit/{event_id} — get single audit event."""

    def get(self, request: HttpRequest, event_id: str) -> JsonResponse:
        if not _require_audit_access(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            client = _build_client(request)
            data = client.get(f"/admin/audit/{event_id}")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
