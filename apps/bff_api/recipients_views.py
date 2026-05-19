import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _handle_sync_error,
    _ok,
    _error,
    _require_storekeeper,
    _require_chief_or_root,
)
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.recipients_api import RecipientsAPI


def _rec(request):
    return RecipientsAPI(_build_client(request))


class RecipientsListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _rec(request)
            params: dict[str, str] = {}
            for key in ("search", "recipient_type", "include_inactive", "include_deleted", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_recipients(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _rec(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.create_recipient(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class RecipientsMergeView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Only chief_storekeeper or root can merge recipients", "forbidden", 403)
        try:
            api = _rec(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.merge_recipients(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class RecipientDetailView(LoginRequiredMixin, View):
    def get(self, request, recipient_id):
        try:
            api = _rec(request)
            data = api.get_recipient(recipient_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, recipient_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _rec(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.update_recipient(recipient_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

    def delete(self, request, recipient_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _rec(request)
            api.delete_recipient(recipient_id)
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
