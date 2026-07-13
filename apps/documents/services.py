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
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

from .models import RenderedDocumentArtifact

CACHE_KEY_PREFIX = "waybill_pdf:"
CACHE_TTL = 3600  # 1 hour

logger = structlog.get_logger()

SIGNATURE_PLACEHOLDER = "_________________/__________________"
DEFAULT_RENDERER_VERSION = "waybill-pdf-v3"
# Cache namespace for the printable layout itself.  This must be bumped with
# every incompatible HTML/CSS pagination layout change, even if deployment
# settings still provide the same DOCUMENT_RENDERER_VERSION.  rev. 7 changed
# pagination from logical-row counts to content-aware visual units.
WAYBILL_LAYOUT_CACHE_VERSION = "layout-v7"

# Content-aware waybill capacities (TZ-V3.1I rev. 7).
# A unit is one visual item-name line. 22/28 are the calibrated first/middle
# baseline capacities for a one-line name. Last-page capacities reserve its
# full signature form and sheet counter, then leave one visual-row safety unit.
NAME_CHARS_PER_VISUAL_LINE = 40
FIRST_PAGE_UNITS = 22
MIDDLE_PAGE_UNITS = 28
LAST_PAGE_UNITS = {
    # Real WeasyPrint calibration with the four-block MOVE form leaves 19
    # units; 20 can already push the static signature/counter to page three.
    "MOVE": 19,
    "ISSUE": 25,
    "ISSUE_RETURN": 25,
    "EXPENSE": 25,
    "WRITE_OFF": 25,
    "DEFAULT": 26,
}
# A single page combines the full first-page header with the last-page form.
# These values include the same one-unit safety reserve as LAST_PAGE_UNITS.
SINGLE_PAGE_UNITS = {
    "MOVE": 15,
    "ISSUE": 19,
    "ISSUE_RETURN": 19,
    "EXPENSE": 19,
    "WRITE_OFF": 19,
    "DEFAULT": 21,
}


class DocumentPdfRenderError(RuntimeError):
    """Raised when Django cannot render/cache a document PDF."""


@dataclass(frozen=True)
class RenderedDocumentResult:
    artifact: RenderedDocumentArtifact
    pdf_bytes: bytes
    cache_hit: bool


def render_document_pdf(document: dict[str, Any], *, force: bool = False) -> RenderedDocumentResult:
    """Render PDF through Django and cache in Django cache (not disk)."""
    identity = _cache_identity(document)
    # rev. 6 (hotfix 09.07.2026): cache_key MUST include renderer_version.
    # Without it, bumping DOCUMENT_RENDERER_VERSION does not invalidate the cache,
    # and old waybills keep returning stale PDFs. Confirmed by storekeeper bug
    # (operation 11673bc0-..., нажал "сформировать накладную", получил PDF v1).
    # template_version and layout namespace are included too so template/CSS
    # pagination changes also bust the cache.
    cache_key = (
        f"{CACHE_KEY_PREFIX}"
        f"{identity['document_id']}:{identity['payload_hash']}"
        f":{identity['renderer_version']}:{identity['template_version']}"
        f":{WAYBILL_LAYOUT_CACHE_VERSION}"
    )

    # Check Django cache
    if not force:
        cached = cache.get(cache_key)
        if cached is not None:
            pdf_bytes, artifact_id = cached
            try:
                artifact = RenderedDocumentArtifact.objects.get(id=artifact_id)
            except RenderedDocumentArtifact.DoesNotExist:
                pass
            else:
                return RenderedDocumentResult(artifact=artifact, pdf_bytes=pdf_bytes, cache_hit=True)

    # Create/reuse artifact record for audit
    identity_dict = _cache_identity(document)
    artifact, _created = RenderedDocumentArtifact.objects.get_or_create(
        document_id=identity_dict["document_id"],
        revision=identity_dict["revision"],
        payload_hash=identity_dict["payload_hash"],
        template_name=identity_dict["template_name"],
        template_version=identity_dict["template_version"],
        renderer_version=identity_dict["renderer_version"],
        defaults={
            "document_type": identity_dict["document_type"],
            "status": RenderedDocumentArtifact.Status.RENDERING,
        },
    )

    try:
        html = render_document_html(document)
        pdf_bytes = _render_html_to_pdf_bytes(html)
    except Exception as exc:
        artifact.status = RenderedDocumentArtifact.Status.FAILED
        artifact.last_error = str(exc)
        artifact.save(update_fields=["status", "last_error", "updated_at"])
        if isinstance(exc, DocumentPdfRenderError):
            raise
        raise DocumentPdfRenderError(str(exc)) from exc

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    # Update artifact without saving pdf_file
    artifact.status = RenderedDocumentArtifact.Status.READY
    artifact.pdf_sha256 = pdf_sha256
    artifact.size_bytes = len(pdf_bytes)
    artifact.rendered_at = timezone.now()
    artifact.last_error = ""
    artifact.save(update_fields=["status", "pdf_sha256", "size_bytes", "rendered_at", "last_error", "updated_at"])

    # Store in Django cache
    cache.set(cache_key, (pdf_bytes, artifact.id), CACHE_TTL)

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

    operation_type = _text(operation.get("type") or payload.get("operation_type")).upper()

    extra_signatures = _build_extra_signatures(operation_type)
    pages = paginate_waybill_lines(lines, operation_type=operation_type)

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

    # MOVE (rev. 4): 4 блока — Операцию разрешил, Водитель, Начальник базы, Груз принял.
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
            {
                "label": "Начальник базы",
                "position_label": "должность",
                "signature_label": "фио/подпись",
            },
            {
                "label": "Груз принял",
                "position_label": "должность",
                "signature_label": "фио/подпись",
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


def _estimated_line_units(line: dict[str, Any]) -> int:
    """Estimate visual item-name lines using conservative word wrapping."""
    words = re.findall(r"\S+", _text(line.get("item_name")))
    if not words:
        return 1

    visual_lines = 1
    current_length = 0
    for word in words:
        # CSS may split an overlong SKU anywhere; model it as 40-character chunks.
        chunks = [word[index:index + NAME_CHARS_PER_VISUAL_LINE]
                  for index in range(0, len(word), NAME_CHARS_PER_VISUAL_LINE)]
        for chunk in chunks:
            chunk_length = len(chunk)
            separator = 1 if current_length else 0
            if current_length + separator + chunk_length <= NAME_CHARS_PER_VISUAL_LINE:
                current_length += separator + chunk_length
            else:
                visual_lines += 1
                current_length = chunk_length
    return visual_lines


def _page_unit_capacity(*, layout: str, operation_type: str) -> int:
    """Return the safe visual-row budget for a rendered page layout."""
    op = (operation_type or "RECEIVE").upper()
    if layout == "first":
        return FIRST_PAGE_UNITS
    if layout == "middle":
        return MIDDLE_PAGE_UNITS
    if layout == "last":
        return LAST_PAGE_UNITS.get(op, LAST_PAGE_UNITS["DEFAULT"])
    if layout == "single":
        return SINGLE_PAGE_UNITS.get(op, SINGLE_PAGE_UNITS["DEFAULT"])
    raise ValueError(f"Unknown waybill page layout: {layout}")


def paginate_waybill_lines(
    lines: list[dict[str, Any]],
    *,
    operation_type: str = "RECEIVE",
) -> list[dict[str, Any]]:
    """
    Paginate waybill lines by visual row units (TZ-V3.1I rev. 7, plan B).

    Each page is rendered as a self-contained <section class="page"> with a
    fixed amount of vertical overhead. Item names consume one unit per
    estimated visual line, preventing wrapped names from pushing signatures
    onto an orphan physical page.

    Layout is selected per page:
        - "first"   → full title (Накладная + Грузоотправитель + Грузополучатель
                      + Основание) + table + short Кладовщик
        - "middle"  → short title (Накладная № X) + table + short Кладовщик
        - "last"    → short title + table + full signature form
                      (Кладовщик + extra blocks per operation type)

    Returns: list[dict[str, Any]] со структурой:
        {"page_number": int, "lines": list[dict], "is_first": bool,
         "is_last": bool, "total_pages": int, "layout": "first"|"middle"|"last"}
    """
    op = (operation_type or "RECEIVE").upper()

    if not lines:
        return [{
            "page_number": 1,
            "lines": [],
            "is_first": True,
            "is_last": True,
            "total_pages": 1,
            "layout": "first",
        }]

    line_units = [_estimated_line_units(line) for line in lines]
    if len(lines) == 1 and line_units[0] > _page_unit_capacity(layout="single", operation_type=op):
        raise DocumentPdfRenderError("Waybill line is too tall for the single-page layout.")
    largest_line = max(line_units)
    max_capacity = max(
        _page_unit_capacity(layout=layout, operation_type=op)
        for layout in ("first", "middle", "last", "single")
    )
    if largest_line > max_capacity:
        raise DocumentPdfRenderError("Waybill line is too tall to fit on one page.")

    single_capacity = _page_unit_capacity(layout="single", operation_type=op)
    if sum(line_units) <= single_capacity:
        return [{
            "page_number": 1,
            "lines": lines,
            "is_first": True,
            "is_last": True,
            "total_pages": 1,
            "layout": "first",
        }]

    def take_prefix(end: int, capacity: int) -> int:
        used = 0
        index = 0
        while index < end and used + line_units[index] <= capacity:
            used += line_units[index]
            index += 1
        return index

    # Reserve the full last-page form first, while keeping at least one line
    # for the required full-header first page. Sparse middle pages are safer
    # than overflowing a last page and creating an orphan signature sheet.
    last_start = len(lines)
    last_used = 0
    last_capacity = _page_unit_capacity(layout="last", operation_type=op)
    while last_start > 1 and last_used + line_units[last_start - 1] <= last_capacity:
        last_start -= 1
        last_used += line_units[last_start]
    if last_used == 0:
        raise DocumentPdfRenderError("Waybill line is too tall for the last-page layout.")

    first_end = take_prefix(last_start, _page_unit_capacity(layout="first", operation_type=op))
    if first_end == 0:
        raise DocumentPdfRenderError("Waybill line is too tall for the first-page layout.")

    pages_data: list[dict[str, Any]] = [{"lines": lines[:first_end], "layout": "first"}]
    middle_start = first_end
    middle_capacity = _page_unit_capacity(layout="middle", operation_type=op)
    while middle_start < last_start:
        middle_end = middle_start
        used = 0
        while middle_end < last_start and used + line_units[middle_end] <= middle_capacity:
            used += line_units[middle_end]
            middle_end += 1
        if middle_end == middle_start:
            raise DocumentPdfRenderError("Waybill line is too tall for the middle-page layout.")
        pages_data.append({"lines": lines[middle_start:middle_end], "layout": "middle"})
        middle_start = middle_end
    pages_data.append({"lines": lines[last_start:], "layout": "last"})

    total_pages = len(pages_data)
    result: list[dict[str, Any]] = []
    for idx, page in enumerate(pages_data):
        result.append({
            "page_number": idx + 1,
            "lines": page["lines"],
            "is_first": idx == 0,
            "is_last": idx == total_pages - 1,
            "total_pages": total_pages,
            "layout": page["layout"],
        })
    return result


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


def render_document_pdf_streaming(document: dict[str, Any]) -> HttpResponse:
    """Render waybill PDF in-memory and return as streaming response."""
    result = render_document_pdf(document)
    filename = build_document_pdf_filename(document)
    response = HttpResponse(result.pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["X-Document-Pdf-Cache"] = "hit" if result.cache_hit else "miss"
    return response


def get_cached_or_render(document_id: str, payload_hash: str) -> bytes | None:
    """Get PDF from cache or return None if not cached."""
    cache_key = f"{CACHE_KEY_PREFIX}{document_id}:{payload_hash}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached[0]
    return None
