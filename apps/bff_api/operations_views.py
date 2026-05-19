import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _handle_sync_error,
    _ok,
    _error,
    _require_storekeeper,
)
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.operations_api import OperationsAPI


def _ops(request):
    return OperationsAPI(_build_client(request))


class OperationsListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _ops(request)
            params: dict[str, str] = {}
            for key in (
                "site_id", "type", "status", "created_by_user_id",
                "effective_after", "effective_before",
                "created_after", "created_before",
                "updated_after", "updated_before",
                "search", "page", "page_size",
            ):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_operations_page(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ops(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.create_operation(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class OperationDetailView(LoginRequiredMixin, View):
    def delete(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ops(request)
            api.delete_operation(operation_id)
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def get(self, request, operation_id):
        try:
            api = _ops(request)
            data = api.get_operation(operation_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ops(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.update_operation(operation_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class OperationEffectiveAtView(LoginRequiredMixin, View):
    def patch(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ops(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.client.patch(
                f"/operations/{operation_id}/effective-at",
                json=payload,
            )
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class OperationSubmitView(LoginRequiredMixin, View):
    def post(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ops(request)
            payload = json.loads(request.body) if request.body else {"submit": True}
            data = api.submit_operation(operation_id, payload=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class OperationCancelView(LoginRequiredMixin, View):
    def post(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ops(request)
            payload = json.loads(request.body) if request.body else {"cancel": True}
            data = api.cancel_operation(operation_id, payload=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class OperationAcceptLinesView(LoginRequiredMixin, View):
    def post(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ops(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.accept_operation_lines(operation_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)
