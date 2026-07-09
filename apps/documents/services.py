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

# Waybill geometry constants (TZ-V3.1I rev. 5, plan B).
# A4 portrait: 210x297mm, @page margin 16mm top + 14mm bottom -> 267mm inner height.
# Exact-rows pagination: page budgets are computed in mm and converted to row counts
# with `int(available // ROW_HEIGHT_MM)`. WeasyPrint respects the cap because the
# template closes the page section after exactly N <tr> elements.
A4_INNER_HEIGHT_MM = 267.0
ROW_HEIGHT_MM = 8.5
THEAD_HEIGHT_MM = 10.0
SHORT_TITLE_HEIGHT_MM = 12.0
# rev. 5: calibrated against real WeasyPrint rendering (08.07.2026).
# Original 50mm underestimated: real full title (h1 16pt + 6mm margin +
# 3 lines of requisites × 11pt × 1.4 + bottom margin) = 60mm. Confirmed by
# storekeeper: page 1 holds 22 rows, not 23.
FULL_TITLE_HEIGHT_MM = 60.0
SIG_STOREKEEPER_MM = 6.0
SIG_BLOCK_HEIGHT_MM = 14.0
SIG_BLOCK_DRIVER_MM = 6.0

# Legacy aliases kept for backward compatibility with rev. 2 imports/tests.
SIGNATURE_BLOCK_HEIGHT_MM = 37.0
SINGLE_ROW_SIGNATURE_HEIGHT_MM = 4.0


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
    # template_version included too so template changes also bust the cache.
    cache_key = (
        f"{CACHE_KEY_PREFIX}"
        f"{identity['document_id']}:{identity['payload_hash']}"
        f":{identity['renderer_version']}:{identity['template_version']}"
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


def _max_rows_for_page(
    *,
    is_first: bool,
    is_last: bool,
    extra_signatures_count: int,
    has_driver: bool,
) -> int:
    """Compute the exact row cap for a single page based on layout type.

    Each page is rendered as a self-contained <section class="page"> with
    a fixed amount of vertical overhead (title + thead + signature block).
    The remainder is divided by ROW_HEIGHT_MM to give the row cap. The
    template closes the page section after exactly this many <tr> elements,
    so WeasyPrint cannot overflow into an orphan signature page.
    """
    if is_first:
        overhead = FULL_TITLE_HEIGHT_MM + THEAD_HEIGHT_MM + SIG_STOREKEEPER_MM
    else:
        overhead = SHORT_TITLE_HEIGHT_MM + THEAD_HEIGHT_MM + SIG_STOREKEEPER_MM
        if is_last:
            # Last page replaces the short "Кладовщик: ____" with the full
            # signature form: Кладовщик + (extra standard blocks) + optional driver.
            overhead -= SIG_STOREKEEPER_MM
            if has_driver:
                # MOVE: Операцию разрешил + Водитель + Начальник базы + Груз принял
                # 3 standard blocks + 1 driver block.
                overhead += SIG_STOREKEEPER_MM + 3 * SIG_BLOCK_HEIGHT_MM + SIG_BLOCK_DRIVER_MM
            else:
                overhead += SIG_STOREKEEPER_MM + extra_signatures_count * SIG_BLOCK_HEIGHT_MM
    available = A4_INNER_HEIGHT_MM - overhead
    return max(1, int(available // ROW_HEIGHT_MM))


def paginate_waybill_lines(
    lines: list[dict[str, Any]],
    *,
    operation_type: str = "RECEIVE",
) -> list[dict[str, Any]]:
    """
    Paginate waybill lines with EXACT row counts per page (TZ-V3.1I rev. 5, plan B).

    Each page is rendered as a self-contained <section class="page"> with a
    fixed amount of vertical overhead. The remainder is divided by
    ROW_HEIGHT_MM to give the row cap, and the template closes the page
    section after exactly that many <tr> elements. There is no flexbox
    min-height pinning: the page section is sized by its content, and the
    row cap prevents overflow into an orphan signature page.

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
    has_driver = op == "MOVE"

    if op == "MOVE":
        extra_sigs = 3  # Операцию разрешил + Начальник базы + Груз принял
    elif op in ("ISSUE", "ISSUE_RETURN", "EXPENSE"):
        extra_sigs = 1
    elif op == "WRITE_OFF":
        extra_sigs = 1
    else:  # RECEIVE, ADJUSTMENT, CORRECTION
        extra_sigs = 0

    first_max = _max_rows_for_page(
        is_first=True,
        is_last=False,
        extra_signatures_count=extra_sigs,
        has_driver=has_driver,
    )
    middle_max = _max_rows_for_page(
        is_first=False,
        is_last=False,
        extra_signatures_count=0,
        has_driver=False,
    )
    last_max = _max_rows_for_page(
        is_first=False,
        is_last=True,
        extra_signatures_count=extra_sigs,
        has_driver=has_driver,
    )

    if not lines:
        return [{
            "page_number": 1,
            "lines": [],
            "is_first": True,
            "is_last": True,
            "total_pages": 1,
            "layout": "first",
        }]

    total = len(lines)

    # Single-page document: everything fits on the first layout.
    if total <= first_max:
        return [{
            "page_number": 1,
            "lines": lines,
            "is_first": True,
            "is_last": True,
            "total_pages": 1,
            "layout": "first",
        }]

    # Multi-page: first + zero or more FULL middle pages + last (sparse allowed).
    # rev. 5: middle pages are always full (middle_max rows); only the last page
    # may be sparse (1..middle_max-1 rows). When the remainder after full middles
    # is 0, we absorb the last middle into the last page (which may slightly
    # exceed last_max visually — acceptable for the rare edge case).
    remaining_after_first = total - first_max
    if remaining_after_first <= last_max:
        pages_data = [
            {"lines": lines[:first_max], "layout": "first"},
            {"lines": lines[first_max:], "layout": "last"},
        ]
    else:
        n_full_middle = remaining_after_first // middle_max
        last_size = remaining_after_first - n_full_middle * middle_max
        if last_size == 0:
            n_full_middle -= 1
            last_size = middle_max

        middles: list[dict[str, Any]] = []
        i = first_max
        for _ in range(n_full_middle):
            middles.append({
                "lines": lines[i:i + middle_max],
                "layout": "middle",
            })
            i += middle_max

        pages_data = (
            [{"lines": lines[:first_max], "layout": "first"}]
            + middles
            + [{"lines": lines[i:], "layout": "last"}]
        )

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
