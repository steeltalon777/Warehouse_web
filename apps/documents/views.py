from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.views import View

from apps.common.mixins import SyncContextMixin
from apps.sync_client.documents_api import DocumentsAPI
from apps.sync_client.exceptions import SyncServerAPIError


DOCUMENT_TYPE_LABELS = {
    "waybill": "Накладная",
    "acceptance_certificate": "Акт приёмки",
    "act": "Акт",
    "invoice": "Счёт",
}
ALLOWED_OPERATION_DOCUMENT_TYPES = {"waybill", "acceptance_certificate", "act", "invoice"}


def present_document(document: dict[str, Any]) -> dict[str, Any]:
    document_type = str(document.get("document_type") or "")
    return {
        **document,
        "type_label": DOCUMENT_TYPE_LABELS.get(document_type, document_type or "Документ"),
    }


class GenerateOperationDocumentView(SyncContextMixin, View):
    def post(self, request, operation_id: str):
        document_type = str(request.POST.get("document_type") or "waybill").strip()
        if document_type not in ALLOWED_OPERATION_DOCUMENT_TYPES:
            messages.error(request, "Неизвестный тип документа.")
            return redirect("operations:detail", operation_id=operation_id)

        try:
            result = DocumentsAPI(self.client).generate_operation_document(
                operation_id,
                document_type=document_type,
                auto_finalize=True,
            )
        except SyncServerAPIError as exc:
            messages.error(request, str(exc) or "Не удалось сформировать документ.")
            return redirect("operations:detail", operation_id=operation_id)

        document = result.get("document") if isinstance(result, dict) else None
        document_id = document.get("id") if isinstance(document, dict) else None
        if not document_id:
            messages.error(request, "SyncServer не вернул ID документа.")
            return redirect("operations:detail", operation_id=operation_id)

        return redirect("documents:pdf", document_id=document_id)


class DocumentPdfView(SyncContextMixin, View):
    def get(self, request, document_id: str):
        try:
            pdf_bytes, headers = DocumentsAPI(self.client).render_document_pdf(document_id)
        except SyncServerAPIError as exc:
            if exc.status_code == 404:
                raise Http404("Документ не найден.") from exc
            messages.error(request, str(exc) or "Не удалось открыть PDF.")
            return redirect("operations:list")

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            headers.get("content-disposition")
            or f'inline; filename="document_{document_id}.pdf"'
        )
        return response
