"""Django PDF renderer/cache for SyncServer document payloads.

SyncServer remains the authoritative source of document metadata and immutable
payload. This module stores only technical web artifacts derived from that
payload: HTML render context and cached PDF bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from .models import RenderedDocumentArtifact

logger = structlog.get_logger()

SIGNATURE_PLACEHOLDER = "_________________/__________________"
DEFAULT_RENDERER_VERSION = "waybill-pdf-v1"


class DocumentPdfRenderError(RuntimeError):
    """Raised when Django cannot render/cache a document PDF."""


@dataclass(frozen=True)
class RenderedDocumentResult:
    artifact: RenderedDocumentArtifact
    pdf_bytes: bytes
    cache_hit: bool


def render_document_pdf(document: dict[str, Any], *, force: bool = False) -> RenderedDocumentResult:
    """Render PDF through Django and cache it by document payload/template identity."""
    identity = _cache_identity(document)
    artifact, _created = RenderedDocumentArtifact.objects.get_or_create(
        document_id=identity["document_id"],
        revision=identity["revision"],
        payload_hash=identity["payload_hash"],
        template_name=identity["template_name"],
        template_version=identity["template_version"],
        renderer_version=identity["renderer_version"],
        defaults={
            "document_type": identity["document_type"],
            "status": RenderedDocumentArtifact.Status.RENDERING,
        },
    )

    if not force and artifact.is_ready and artifact.pdf_file.storage.exists(artifact.pdf_file.name):
        with artifact.pdf_file.open("rb") as pdf_file:
            return RenderedDocumentResult(artifact=artifact, pdf_bytes=pdf_file.read(), cache_hit=True)

    try:
        html = render_document_html(document)
        pdf_bytes = _render_html_to_pdf_bytes(html)
    except Exception as exc:  # pragma: no cover - concrete message is tested through wrapper paths
        artifact.status = RenderedDocumentArtifact.Status.FAILED
        artifact.last_error = str(exc)
        artifact.save(update_fields=["status", "last_error", "updated_at"])
        if isinstance(exc, DocumentPdfRenderError):
            raise
        raise DocumentPdfRenderError(str(exc)) from exc

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    filename = build_document_pdf_filename(document)

    artifact.document_type = identity["document_type"]
    artifact.status = RenderedDocumentArtifact.Status.READY
    artifact.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
    artifact.pdf_sha256 = pdf_sha256
    artifact.size_bytes = len(pdf_bytes)
    artifact.rendered_at = timezone.now()
    artifact.last_error = ""
    artifact.save()

    return RenderedDocumentResult(artifact=artifact, pdf_bytes=pdf_bytes, cache_hit=False)


def render_document_html(document: dict[str, Any]) -> str:
    """Render document HTML through Django templates."""
    document_type = str(document.get("document_type") or "waybill")
    if document_type != "waybill":
        raise DocumentPdfRenderError("Django PDF renderer currently supports only waybill documents.")
    return render_to_string("documents/waybill_pdf.html", build_waybill_context(document))


def build_waybill_context(document: dict[str, Any]) -> dict[str, Any]:
    """Build template context matching the approved waybill MVP layout."""
    payload = _payload(document)
    operation = payload.get("operation") if isinstance(payload.get("operation"), dict) else {}

    operation_display_number = (
        _text(payload.get("operation_display_number"))
        or _text(operation.get("display_number"))
        or _compute_display_number(_document_site_id(document, payload), payload.get("operation_created_at") or operation.get("created_at"))
        or _text(document.get("document_number"))
        or _text(document.get("id"))
    )
    title = f"Накладная № {operation_display_number}"

    lines = [_normalize_line(line, index) for index, line in enumerate(payload.get("lines") or [], start=1)]
    pages = paginate_waybill_lines(lines)

    operation_type = _text(operation.get("type") or payload.get("operation_type")).upper()

    extra_signatures = _build_extra_signatures(operation_type)

    return {
        "document_id": document.get("id"),
        "title": title,
        "operation_display_number": operation_display_number,
        "operation_type": operation_type,
        "shipper_requisites": getattr(settings, "DOCUMENT_SHIPPER_REQUISITES", ""),
        "consignee_label": _consignee_label(payload),
        "basis_label": _basis_label(payload),
        "pages": pages,
        "total_pages": len(pages),
        "signature_placeholder": SIGNATURE_PLACEHOLDER,
        "extra_signatures": extra_signatures,
    }


def _build_extra_signatures(operation_type: str) -> list[dict[str, Any]]:
    """Return extra signature blocks for the waybill footer based on operation type.

    Extra signatures appear only on the last page (or single page).
    Кладовщик appears on every page regardless.
    """
    op = operation_type.upper()

    # MOVE: operation approved + driver
    if op == "MOVE":
        return [
            {
                "label": "Операцию разрешил",
                "position_label": "должность",
                "signature_label": "фио/подпись",
            },
            {
                "label": "Водитель",
                "driver_signature": True,
            },
        ]

    # WRITE_OFF: operation approved
    if op == "WRITE_OFF":
        return [
            {
                "label": "Операцию разрешил",
                "position_label": "должность",
                "signature_label": "фио/подпись",
            },
        ]

    # ISSUE / ISSUE_RETURN / EXPENSE: received by
    if op in ("ISSUE", "ISSUE_RETURN", "EXPENSE"):
        return [
            {
                "label": "Получил",
                "position_label": "должность",
                "signature_label": "фио/подпись",
            },
        ]

    # RECEIVE, CORRECTION, ADJUSTMENT: no extra signatures
    return []


def paginate_waybill_lines(
    lines: list[dict[str, Any]],
    *,
    first_page_capacity: int = 24,
    continuation_capacity: int = 30,
) -> list[dict[str, Any]]:
    """Chunk lines so every rendered table/page gets its own storekeeper signature."""
    pages: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_weight = 0
    current_capacity = first_page_capacity

    def flush() -> None:
        nonlocal current, current_weight, current_capacity
        pages.append({"page_number": len(pages) + 1, "lines": current, "is_first": len(pages) == 0})
        current = []
        current_weight = 0
        current_capacity = continuation_capacity

    for line in lines:
        weight = _line_weight(line)
        if current and current_weight + weight > current_capacity:
            flush()
        current.append(line)
        current_weight += weight

    if current or not pages:
        flush()

    total_pages = len(pages)
    for page in pages:
        page["total_pages"] = total_pages
        page["is_last"] = (page["page_number"] == total_pages)
    return pages


def build_document_pdf_filename(document: dict[str, Any]) -> str:
    payload = _payload(document)
    number = (
        _text(payload.get("operation_display_number"))
        or _text((payload.get("operation") or {}).get("display_number") if isinstance(payload.get("operation"), dict) else None)
        or _text(document.get("document_number"))
        or _text(document.get("id"))
        or "document"
    )
    return f"nakladnaya_{_safe_filename_part(number)}.pdf"


def _cache_identity(document: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(document)
    document_type = str(document.get("document_type") or "waybill")
    template_name = str(document.get("template_name") or f"{document_type}_v1")
    template_version = str(document.get("template_version") or "")
    renderer_version = str(getattr(settings, "DOCUMENT_RENDERER_VERSION", DEFAULT_RENDERER_VERSION))
    payload_hash = str(document.get("payload_hash") or _hash_payload(payload))
    return {
        "document_id": str(document.get("id") or ""),
        "revision": int(document.get("revision") or 0),
        "document_type": document_type,
        "payload_hash": payload_hash,
        "template_name": template_name,
        "template_version": template_version,
        "renderer_version": renderer_version,
    }


def _render_html_to_pdf_bytes(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover - depends on runtime image packages
        raise DocumentPdfRenderError("WeasyPrint is not installed or native PDF dependencies are missing.") from exc

    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()


def _payload(document: dict[str, Any]) -> dict[str, Any]:
    payload = document.get("payload") or {}
    return payload if isinstance(payload, dict) else {}


def _hash_payload(payload: dict[str, Any]) -> str:
    payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()


def _normalize_line(line: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "line_number": line.get("line_number") or index,
        "item_name": _text(line.get("item_name") or line.get("item_name_snapshot")) or "—",
        "unit": _text(line.get("unit_symbol") or line.get("unit_name") or line.get("unit_symbol_snapshot")) or "—",
        "quantity": _format_quantity(line.get("quantity") or line.get("qty")),
    }


def _format_quantity(value: Any) -> str:
    if value is None or value == "":
        return "0"
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    text = format(decimal_value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _line_weight(line: dict[str, Any]) -> int:
    name_length = len(str(line.get("item_name") or ""))
    return max(1, 1 + name_length // 70)


def _consignee_label(payload: dict[str, Any]) -> str:
    if _text(payload.get("consignee_label")):
        return _text(payload.get("consignee_label"))
    receiver = payload.get("receiver") if isinstance(payload.get("receiver"), dict) else None
    if receiver:
        return _text(receiver.get("site_name") or receiver.get("site_code")) or "—"
    recipient = payload.get("recipient") if isinstance(payload.get("recipient"), dict) else None
    if recipient:
        return _text(recipient.get("recipient_name")) or "—"
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else None
    if sender:
        return _text(sender.get("site_name") or sender.get("site_code")) or "—"
    return "—"


def _basis_label(payload: dict[str, Any]) -> str:
    if _text(payload.get("basis_label")):
        return _text(payload.get("basis_label"))
    basis = payload.get("basis") if isinstance(payload.get("basis"), dict) else None
    if basis and _text(basis.get("label")):
        return _text(basis.get("label"))
    operation_type = _text(payload.get("operation_type_label") or payload.get("operation_type")) or "Операция"
    return operation_type


def _document_site_id(document: dict[str, Any], payload: dict[str, Any]) -> int | None:
    for value in [document.get("site_id"), (payload.get("sender") or {}).get("site_id") if isinstance(payload.get("sender"), dict) else None]:
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _compute_display_number(site_id: int | None, created_at: Any) -> str | None:
    if site_id is None or not created_at:
        return None
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return f"{site_id}/{dt.strftime('%H%M')}/{dt.strftime('%d%m%y')}"


def _safe_filename_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-zА-Яа-я0-9._-]+", "_", value.strip())
    return normalized.strip("._-") or "document"


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
