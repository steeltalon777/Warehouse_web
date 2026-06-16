"""Custom Django admin views for SyncServer audit events.

These views display AuditEvent data from SyncServer via BFF API.
They are NOT ModelAdmin — data lives in SyncServer, not in Django.
"""

from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _require_root,
)
from apps.common.permissions import can_manage_catalog
from apps.sync_client.exceptions import SyncServerAPIError


def _has_audit_access(user) -> bool:
    return _require_root(user) or can_manage_catalog(user)


@method_decorator(staff_member_required, name="dispatch")
class AdminAuditEventListView(View):
    """Admin view: list SyncServer audit events with filters.

    URL: /admin/audit-events/
    Template: admin/audit_events_list.html
    """

    template_name = "admin/audit_events_list.html"

    def get(self, request: HttpRequest):
        if not _has_audit_access(request.user):
            return render(
                request,
                "admin/audit_events_list.html",
                {"error": "Доступ запрещён. Требуются права root или chief_storekeeper."},
            )

        try:
            client = _build_client(request)
            params: dict[str, str] = {}
            for key in (
                "event_type", "actor_user_id", "site_id",
                "entity_type", "entity_id",
                "date_from", "date_to", "page",
            ):
                val = request.GET.get(key)
                if val:
                    params[key] = val

            data = client.get("/admin/audit", params=params)
            return render(request, self.template_name, {
                "audit_events": data.get("items", []),
                "total_count": data.get("total_count", 0),
                "page": data.get("page", 1),
                "page_size": data.get("page_size", 50),
                "filters": request.GET,
            })
        except SyncServerAPIError as exc:
            return render(
                request,
                self.template_name,
                {"error": f"Ошибка SyncServer: {exc}"},
            )


@method_decorator(staff_member_required, name="dispatch")
class AdminAuditEventDetailView(View):
    """Admin view: single SyncServer audit event detail.

    URL: /admin/audit-events/<event_id>/
    Template: admin/audit_event_detail.html
    """

    template_name = "admin/audit_event_detail.html"

    def get(self, request: HttpRequest, event_id: str):
        if not _has_audit_access(request.user):
            return render(
                request,
                self.template_name,
                {"error": "Доступ запрещён."},
            )

        try:
            client = _build_client(request)
            data = client.get(f"/admin/audit/{event_id}")
            return render(request, self.template_name, {
                "event": data,
            })
        except SyncServerAPIError as exc:
            return render(
                request,
                self.template_name,
                {"error": f"Ошибка SyncServer: {exc}"},
            )
