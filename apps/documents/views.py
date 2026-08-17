from __future__ import annotations

import time
from typing import Any

import structlog
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.utils.http import content_disposition_header
from django.views import View

from apps.common.mixins import SyncContextMixin
from apps.documents.services import DocumentPdfRenderError, build_document_pdf_filename, render_document_pdf, render_shadow_pdf
from apps.sync_client.documents_api import DocumentsAPI
from apps.sync_client.exceptions import SyncServerAPIError

logger = structlog.get_logger()


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
            return redirect("operations_ssr:detail", operation_id=operation_id)

        try:
            result = DocumentsAPI(self.client).generate_operation_document(
                operation_id,
                document_type=document_type,
                auto_finalize=True,
            )
        except SyncServerAPIError as exc:
            messages.error(request, str(exc) or "Не удалось сформировать документ.")
            return redirect("operations_ssr:detail", operation_id=operation_id)

        document = result.get("document") if isinstance(result, dict) else None
        document_id = document.get("id") if isinstance(document, dict) else None
        if not document_id:
            messages.error(request, "SyncServer не вернул ID документа.")
            return redirect("operations_ssr:detail", operation_id=operation_id)

        return redirect("documents:pdf", document_id=document_id)


class DocumentPdfView(SyncContextMixin, View):
    def get(self, request, document_id: str):
        api = DocumentsAPI(self.client)
        try:
            document = _get_document_with_retry(api, document_id)
        except SyncServerAPIError as exc:
            if exc.status_code == 404:
                raise Http404("Документ не найден.") from exc
            messages.error(request, str(exc) or "Не удалось открыть PDF.")
            return redirect("operations_spa")

        try:
            render_result = render_document_pdf(document)
        except DocumentPdfRenderError as exc:
            messages.error(request, str(exc) or "Не удалось сформировать PDF.")
            return redirect("operations_spa")

        # Phase 6D SHADOW: attempt QDE shadow render (best-effort, never blocks response).
        render_mode = getattr(settings, "DOCUMENTS_RENDER_MODE", "legacy")
        if render_mode == "shadow":
            try:
                render_shadow_pdf(document)
            except Exception:
                logger.exception(
                    "shadow_render_failed",
                    document_id=document_id,
                )

        download = str(request.GET.get("download") or "").lower() in {"1", "true", "yes"}
        filename = build_document_pdf_filename(document)
        response = HttpResponse(render_result.pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = content_disposition_header(download, filename) or (
            f'{"attachment" if download else "inline"}; filename="{filename}"'
        )
        response["X-Document-Pdf-Cache"] = "hit" if render_result.cache_hit else "miss"
        return response


def _get_document_with_retry(api: DocumentsAPI, document_id: str, *, attempts: int = 3) -> dict[str, Any]:
    """Read freshly generated documents with a short retry to avoid open-after-create races."""
    last_error: SyncServerAPIError | None = None
    for attempt in range(attempts):
        try:
            return api.get_document(document_id)
        except SyncServerAPIError as exc:
            if exc.status_code != 404:
                raise
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.15)
    assert last_error is not None
    raise last_error
