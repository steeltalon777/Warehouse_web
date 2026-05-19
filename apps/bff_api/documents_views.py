import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _handle_sync_error,
    _ok,
    _error,
    _require_storekeeper,
)
from apps.sync_client.documents_api import DocumentsAPI
from apps.sync_client.exceptions import SyncServerAPIError


def _docs(request):
    return DocumentsAPI(_build_client(request))


class DocumentGenerateView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _docs(request)
            payload = json.loads(request.body) if request.body else {}
            operation_id = payload.pop("operation_id", None)
            if not operation_id:
                return _error("operation_id is required", "validation_error", 400)
            data = api.generate_operation_document(
                operation_id=operation_id,
                document_type=payload.get("document_type", "waybill"),
                template_name=payload.get("template_name"),
                auto_finalize=payload.get("auto_finalize", False),
                language=payload.get("language", "ru"),
                basis_type=payload.get("basis_type"),
                basis_number=payload.get("basis_number"),
                basis_date=payload.get("basis_date"),
            )
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class DocumentsListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _docs(request)
            params: dict[str, str] = {}
            for key in ("site_id", "document_type", "status", "created_by_user_id",
                        "date_from", "date_to", "offset", "limit"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            response = api.client.get("/documents", params=params)
            return _ok(response)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class DocumentDetailView(LoginRequiredMixin, View):
    def get(self, request, document_id):
        try:
            api = _docs(request)
            data = api.get_document(document_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class DocumentRenderView(LoginRequiredMixin, View):
    def get(self, request, document_id):
        try:
            api = _docs(request)
            fmt = request.GET.get("format", "html")
            if fmt == "pdf":
                content, headers = api.render_document_pdf(document_id)
                response = HttpResponse(content, content_type="application/pdf")
                for key, val in headers.items():
                    response[key] = val
                return response
            data = api.client.get(f"/documents/{document_id}/render", params={"format": "html"})
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class DocumentStatusView(LoginRequiredMixin, View):
    def patch(self, request, document_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _docs(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.client.patch(f"/documents/{document_id}/status", json=payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class OperationDocumentsView(LoginRequiredMixin, View):
    def get(self, request, operation_id):
        try:
            api = _docs(request)
            doc_type = request.GET.get("document_type")
            data = api.list_operation_documents(operation_id, document_type=doc_type)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _docs(request)
            data = api.generate_operation_document(
                operation_id=operation_id,
                document_type=request.GET.get("document_type", "waybill"),
                template_name=request.GET.get("template_name"),
                auto_finalize=request.GET.get("auto_finalize", "false").lower() == "true",
                language=request.GET.get("language", "ru"),
                basis_type=request.GET.get("basis_type"),
                basis_number=request.GET.get("basis_number"),
                basis_date=request.GET.get("basis_date"),
            )
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
