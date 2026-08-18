"""Django PDF renderer/cache for SyncServer document payloads.

SyncServer remains the authoritative source of document metadata and immutable
payload. This module stores only technical web artifacts derived from that
payload: HTML render context and cached PDF bytes.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import jsonschema
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
WAYBILL_LAYOUT_CACHE_VERSION = "layout-v7.1"

# Canonical legacy render axes (TZ-QDE_INTEGRATION_READINESS.md §5.2).
# Used by the legacy Django/WeasyPrint render path and by Phase 6B backfill
# of historical artifact rows. engine_version falls back to
# DEFAULT_RENDERER_VERSION only when the historical renderer_version is empty.
DEFAULT_LEGACY_AXES = {
    "engine": "django-legacy",
    "engine_version": DEFAULT_RENDERER_VERSION,
    "backend": "weasyprint",
    # Actual Warehouse_web legacy WeasyPrint version: requirements.txt pins
    # weasyprint>=66,<67; the dev/stand image installs 66.0.
    "backend_version": "66.0",
    "document_contract": "warehouse.operation-document/v2",
    "template_id": "waybill_v1",
    "template_version": "1.0",
    "layout_version": WAYBILL_LAYOUT_CACHE_VERSION,
    "render_role": "legacy",
}

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
        document_contract=DEFAULT_LEGACY_AXES["document_contract"],
        template_id=identity_dict["template_id"],
        template_version=identity_dict["template_version"],
        engine=DEFAULT_LEGACY_AXES["engine"],
        engine_version=identity_dict["renderer_version"],
        backend=DEFAULT_LEGACY_AXES["backend"],
        backend_version=DEFAULT_LEGACY_AXES["backend_version"],
        defaults={
            "document_type": identity_dict["document_type"],
            "renderer_version": identity_dict["renderer_version"],
            "layout_version": DEFAULT_LEGACY_AXES["layout_version"],
            "render_role": DEFAULT_LEGACY_AXES["render_role"],
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

    # Fill the full-header first page before reserving the final form. Keep one
    # line for the required last-page layout; otherwise a multi-page document
    # could incorrectly turn into a first-page-only layout.
    first_end = take_prefix(len(lines) - 1, _page_unit_capacity(layout="first", operation_type=op))
    if first_end == 0:
        raise DocumentPdfRenderError("Waybill line is too tall for the first-page layout.")

    # Reserve the full last-page form only from the remaining tail. It must
    # never consume a line already assigned to the first page.
    last_start = len(lines)
    last_used = 0
    last_capacity = _page_unit_capacity(layout="last", operation_type=op)
    while last_start > first_end and last_used + line_units[last_start - 1] <= last_capacity:
        last_start -= 1
        last_used += line_units[last_start]
    if last_used == 0:
        raise DocumentPdfRenderError("Waybill line is too tall for the last-page layout.")

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
    template_id = str(document.get("template_name") or f"{document_type}_v1")
    template_version = str(document.get("template_version") or "")
    renderer_version = str(getattr(settings, "DOCUMENT_RENDERER_VERSION", DEFAULT_RENDERER_VERSION))
    payload_hash = str(document.get("payload_hash") or _hash_payload(payload))
    return {
        "document_id": str(document.get("id") or ""),
        "revision": int(document.get("revision") or 0),
        "document_type": document_type,
        "payload_hash": payload_hash,
        "template_id": template_id,
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
    return f"{dt.strftime('%d%m%y')}/{dt.strftime('%H%M')}/{site_id}"


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


# =====================================================================
# QDE (Quartermaster Document Engine) integration — Phase 6A service layer
# =====================================================================
# ADR-0032 D1-D8 + TZ-QDE_INTEGRATION_READINESS §6.5/§7. Service layer only:
# no view wiring, no artifact persistence, no legacy fallback. QDE is invoked
# strictly through its CLI subprocess (no in-process QDE imports, ADR-0032 D3).

QDE_ENGINE_CONTRACT_VERSION = "1.0.0"
QDE_LOCALE = "ru-RU"
QDE_RENDER_PROFILE = "print"
QDE_OUTPUT_FORMAT = "pdf"
QDE_TIMEOUT_RETRY_AFTER_SECONDS = 5

# Canonical QDE cache namespace (TZ §5.4). Never intersects with the legacy
# "waybill_pdf:" namespace; the legacy namespace stays untouched for Phase 6D
# SHADOW and rollback.
QDE_CACHE_KEY_PREFIX = "qde_pdf:"


def build_qde_cache_key(
    *,
    document_id: str,
    revision: int,
    payload_hash: str,
    document_contract: str,
    template_id: str,
    template_version: str,
    engine: str,
    engine_version: str,
    backend: str,
    backend_version: str,
) -> str:
    """Build the canonical QDE cache key from the full render identity.

    Canonical format (TZ §5.4):
        qde_pdf:{document_id}:{revision}:{payload_hash}:{document_contract}:
        {template_id}@{template_version}:{engine}@{engine_version}:
        {backend}@{backend_version}

    Every identity axis is mandatory. render_role, status and layout_version
    are deliberately NOT part of the key.
    """
    return (
        f"{QDE_CACHE_KEY_PREFIX}{document_id}:{revision}:{payload_hash}:{document_contract}:"
        f"{template_id}@{template_version}:{engine}@{engine_version}:{backend}@{backend_version}"
    )


def build_legacy_waybill_cache_key(
    *,
    document_id: str,
    payload_hash: str,
    renderer_version: str,
    template_version: str,
) -> str:
    """Build the legacy cache key (TZ §5.4), unchanged for backward compat.

        waybill_pdf:{document_id}:{payload_hash}:{renderer_version}:
        {template_version}:layout-v7.1
    """
    return (
        f"{CACHE_KEY_PREFIX}{document_id}:{payload_hash}:{renderer_version}:"
        f"{template_version}:{WAYBILL_LAYOUT_CACHE_VERSION}"
    )

# Bundled copy of the canonical QDE envelope schema (TZ §7.3):
# QuartermasterDocumentEngine/contracts/envelope/v1/envelope.schema.json
QDE_ENVELOPE_SCHEMA_PATH = Path(__file__).parent / "qde" / "envelope_v1.schema.json"
with QDE_ENVELOPE_SCHEMA_PATH.open("r", encoding="utf-8") as _schema_file:
    ENVELOPE_SCHEMA = json.load(_schema_file)

# Subprocess env whitelist (TZ §7.2/§9.2): exactly these keys. Values come from
# Django settings or fixed defaults; Django secrets are never passed through.
QDE_SUBPROCESS_ENV_KEYS = (
    "PATH",
    "LANG",
    "LC_ALL",
    "QM_TEMPLATES_DIR",
    "QM_TYPST_BINARY",
    "QM_FONTS_DIR",
    "TYPST_TIMESTAMP",
)

_TEMPLATE_ID_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TEMPLATE_VERSION_SAFE_PATTERN = re.compile(r"^[0-9]+\.[0-9]+(\.[0-9]+)?$")


class QdeRenderError(Exception):
    """Base class for QDE render failures (ADR-0032 D8 / TZ §7.4).

    Carries the QDE error code, details and the HTTP status mapping so a later
    phase can translate failures to responses without touching this layer.
    """

    code: str = "RENDER_FAILED"
    http_status: int = 500
    retry_after: int | None = None

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Any = None,
        http_status: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.details = details
        self.http_status = http_status or self.http_status
        self.retry_after = retry_after if retry_after is not None else self.retry_after


class QdeValidationError(QdeRenderError):
    """Envelope/payload validation failure (HTTP 400 semantics)."""

    code = "INVALID_PAYLOAD"
    http_status = 400


class QdeUnsupportedContractError(QdeRenderError):
    """Unsupported engine/document contract or output format (HTTP 400)."""

    code = "UNSUPPORTED_ENGINE_CONTRACT"
    http_status = 400


class QdeTemplateError(QdeRenderError):
    """Template not installed / version not installed (HTTP 503)."""

    code = "TEMPLATE_NOT_INSTALLED"
    http_status = 503


class QdeTemplateContractMismatchError(QdeRenderError):
    """Template does not satisfy the envelope document_contract (HTTP 422)."""

    code = "TEMPLATE_CONTRACT_MISMATCH"
    http_status = 422


class QdeBackendUnavailableError(QdeRenderError):
    """Render backend missing/unavailable, incl. missing binary (HTTP 503)."""

    code = "BACKEND_NOT_AVAILABLE"
    http_status = 503


class QdeFontError(QdeRenderError):
    """Required bundled font not available (HTTP 503)."""

    code = "FONT_NOT_AVAILABLE"
    http_status = 503


class QdeAssetError(QdeRenderError):
    """Requested asset not available in the template package (HTTP 422)."""

    code = "ASSET_NOT_AVAILABLE"
    http_status = 422


class QdeRenderFailedError(QdeRenderError):
    """Generic render failure (HTTP 500)."""

    code = "RENDER_FAILED"
    http_status = 500


class QdeTimeoutError(QdeRenderError):
    """Subprocess timed out (HTTP 503 + retry_after semantics)."""

    code = "SUBPROCESS_TIMEOUT"
    http_status = 503
    retry_after = 5


# TZ §7.4: QDE stderr error code → Django wrapper exception class.
QDE_STDERR_CODE_TO_EXCEPTION: dict[str, type[QdeRenderError]] = {
    "INVALID_PAYLOAD": QdeValidationError,
    "UNSUPPORTED_ENGINE_CONTRACT": QdeUnsupportedContractError,
    "UNSUPPORTED_DOCUMENT_CONTRACT": QdeUnsupportedContractError,
    "UNSUPPORTED_OUTPUT_FORMAT": QdeUnsupportedContractError,
    "TEMPLATE_NOT_INSTALLED": QdeTemplateError,
    "TEMPLATE_VERSION_NOT_INSTALLED": QdeTemplateError,
    "TEMPLATE_CONTRACT_MISMATCH": QdeTemplateContractMismatchError,
    "BACKEND_NOT_AVAILABLE": QdeBackendUnavailableError,
    "FONT_NOT_AVAILABLE": QdeFontError,
    "ASSET_NOT_AVAILABLE": QdeAssetError,
    "RENDER_FAILED": QdeRenderFailedError,
}


@dataclass(frozen=True)
class QdeRenderResult:
    """Outcome of a successful QDE render (Phase 6A: no artifact persistence)."""

    pdf_bytes: bytes
    exit_code: int
    stderr_message: str
    elapsed_seconds: float
    page_count: int | None = None


def build_qde_subprocess_env() -> dict[str, str]:
    """Build the deterministic QDE subprocess environment (TZ §7.2/§9.2).

    Whitelist only: PATH/LANG/LC_ALL come from os.environ or fixed defaults;
    QM_* and TYPST_TIMESTAMP come from Django settings. Django secrets
    (SECRET_KEY, DATABASE_URL, SYNC_*_TOKEN, ...) are never passed through.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "QM_TEMPLATES_DIR": str(getattr(settings, "QM_TEMPLATES_DIR", "")),
        "QM_TYPST_BINARY": str(getattr(settings, "QM_TYPST_BINARY", "")),
        "QM_FONTS_DIR": str(getattr(settings, "QM_FONTS_DIR", "")),
        "TYPST_TIMESTAMP": str(getattr(settings, "TYPST_TIMESTAMP", "1700000000")),
    }


def build_qde_envelope(
    document: dict[str, Any],
    *,
    template_map: Mapping[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a canonical QDE envelope from a SyncServer document dict.

    Normalization rules (ADR-0032 D1/D2/D5, TZ §7.1):
    - document_type defaults to "waybill"; locale "ru-RU"; render_profile "print";
      engine_contract_version is fixed at QDE_ENGINE_CONTRACT_VERSION.
    - document_contract comes from settings.QDE_DOCUMENT_CONTRACT.
    - (template_id, template_version) are resolved ONLY through `template_map`
      (default: settings.DOCUMENT_TEMPLATE_MAP). Values from the document dict
      never influence template resolution (SEC-10 mitigation). Mapped values
      are additionally checked against a safe pattern.
    - envelope.document = document["payload"], which must be a dict
      (missing/malformed payload → QdeValidationError).
    - document_id/document_number are copied from the document dict when present.

    The resulting envelope is validated against the bundled QDE envelope schema
    (apps/documents/qde/envelope_v1.schema.json); validation failure raises
    QdeValidationError (HTTP 400 semantics, TZ §7.3).

    `template_map` may be overridden for tests/operator tooling; the production
    path uses the settings default.
    """
    if not isinstance(document, dict):
        raise QdeValidationError("document must be a dict.")
    document_type = _text(document.get("document_type")) or "waybill"

    resolution_map = (
        template_map if template_map is not None else getattr(settings, "DOCUMENT_TEMPLATE_MAP", {})
    )
    try:
        template_id, template_version = resolution_map[document_type]
    except (KeyError, TypeError):
        raise QdeValidationError(f"No QDE template mapping for document_type {document_type!r}.") from None
    _validate_template_reference(template_id, template_version)

    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise QdeValidationError("Document payload is missing or malformed: expected a dict.")

    envelope: dict[str, Any] = {
        "engine_contract_version": QDE_ENGINE_CONTRACT_VERSION,
        "document_contract": getattr(settings, "QDE_DOCUMENT_CONTRACT", "warehouse.operation-document/v2"),
        "document_type": document_type,
        "template_id": template_id,
        "template_version": template_version,
        "locale": QDE_LOCALE,
        "render_profile": QDE_RENDER_PROFILE,
        "document": payload,
    }
    document_id = _text(document.get("id"))
    if document_id:
        envelope["document_id"] = document_id
    document_number = _text(document.get("document_number"))
    if document_number:
        envelope["document_number"] = document_number

    try:
        jsonschema.validate(envelope, ENVELOPE_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise QdeValidationError(f"Envelope validation failed: {exc.message}") from exc

    return envelope


def _validate_template_reference(template_id: Any, template_version: Any) -> None:
    """Reject unsafe template identifiers from the allowlist map (SEC-10)."""
    if (
        not isinstance(template_id, str)
        or not _TEMPLATE_ID_SAFE_PATTERN.fullmatch(template_id)
        or ".." in template_id
    ):
        raise QdeValidationError(f"Unsafe template_id {template_id!r} in template map.")
    if not isinstance(template_version, str) or not _TEMPLATE_VERSION_SAFE_PATTERN.fullmatch(template_version):
        raise QdeValidationError(f"Unsafe template_version {template_version!r} in template map.")


def render_via_qde(
    document: dict[str, Any] | None = None,
    *,
    template_map: Mapping[str, tuple[str, str]] | None = None,
    envelope: dict[str, Any] | None = None,
) -> QdeRenderResult:
    """Render a document PDF through the QDE CLI subprocess.

    Invocation (TZ §7.2, ADR-0032 D3/D8): argv-only, shell=False, private temp
    dir via tempfile.mkdtemp(prefix="qde-", dir="/tmp") with mode 0700, whitelist
    env (build_qde_subprocess_env), timeout from settings.QDE_SUBPROCESS_TIMEOUT_SECONDS,
    cleanup in `finally`. A pre-built envelope may be passed instead of a document
    dict (tests/operator tooling); the public entry builds the envelope itself.

    QDE failures are NEVER silently replaced by the legacy renderer: any failure
    raises the mapped QdeRenderError subclass (TZ §7.4); timeout raises
    QdeTimeoutError (503 semantics); missing binary raises QdeBackendUnavailableError.
    """
    if envelope is None:
        if document is None:
            raise QdeValidationError("render_via_qde requires a document dict or a pre-built envelope.")
        envelope = build_qde_envelope(document, template_map=template_map)

    workdir = tempfile.mkdtemp(prefix="qde-", dir=tempfile.gettempdir())
    os.chmod(workdir, 0o700)
    envelope_path = os.path.join(workdir, "envelope.json")
    output_path = os.path.join(workdir, "output.pdf")
    argv = [
        "python",
        "-m",
        "qm_cli.main",
        "render",
        "--input",
        envelope_path,
        "--output",
        output_path,
        "--format",
        QDE_OUTPUT_FORMAT,
    ]
    timeout = float(getattr(settings, "QDE_SUBPROCESS_TIMEOUT_SECONDS", 15))
    try:
        with open(envelope_path, "w", encoding="utf-8") as envelope_file:
            json.dump(envelope, envelope_file, ensure_ascii=False)

        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                timeout=timeout,
                env=build_qde_subprocess_env(),
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise QdeTimeoutError(
                f"QDE render timed out after {timeout:g}s.",
                details={"timeout_seconds": timeout},
                retry_after=QDE_TIMEOUT_RETRY_AFTER_SECONDS,
            ) from exc
        except OSError as exc:
            raise QdeBackendUnavailableError(
                f"QDE subprocess could not be started: {exc}",
                details={"argv": argv},
            ) from exc
        elapsed_seconds = time.monotonic() - started

        stderr_message = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        if completed.returncode == 0:
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                with open(output_path, "rb") as pdf_file:
                    pdf_bytes = pdf_file.read()
                return QdeRenderResult(
                    pdf_bytes=pdf_bytes,
                    exit_code=0,
                    stderr_message=stderr_message,
                    elapsed_seconds=elapsed_seconds,
                    page_count=None,  # pypdf is not a Warehouse_web dependency in Phase 6A
                )
            raise QdeRenderFailedError(
                "QDE exited 0 but produced no PDF output.",
                details={"exit_code": 0, "stderr": stderr_message},
            )
        raise _qde_error_from_stderr(stderr_message, exit_code=completed.returncode)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _qde_error_from_stderr(stderr_message: str, *, exit_code: int) -> QdeRenderError:
    """Map a non-zero QDE exit to the TZ §7.4 exception hierarchy."""
    code: str | None = None
    message = stderr_message or "QDE render failed."
    details: Any = None
    parsed: Any = None
    if stderr_message:
        try:
            parsed = json.loads(stderr_message)
        except json.JSONDecodeError:
            # QDE may prefix log lines before the final JSON error object.
            match = re.search(r"\{.*\}", stderr_message, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    parsed = None
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            if not isinstance(code, str):
                code = None
            message = _text(error.get("message")) or message
            details = error.get("details")
    exception_class = QDE_STDERR_CODE_TO_EXCEPTION.get(code, QdeRenderFailedError)
    return exception_class(
        f"QDE render failed: {message}",
        code=code,
        details=details,
    )


# =====================================================================
# Phase 6D: SHADOW integration — shadow render + structural comparison
# =====================================================================
# TZ-QDE_INTEGRATION_READINESS §6.3/§10.4. Shadow mode: QDE renders
# alongside legacy; shadow artifact persisted; structural comparison
# available for operator commands. USER RESPONSE = LEGACY PDF always.


def render_shadow_pdf(document: dict[str, Any]) -> RenderedDocumentResult | None:
    """Attempt QDE shadow render + artifact persistence.

    Returns RenderedDocumentResult on success, None on any failure.
    NEVER raises — shadow path is best-effort by design (TZ §6.3).

    Shadow artifacts are immutable once READY: same identity never overwrites
    an existing READY shadow artifact's PDF/hash/render_role.
    """
    identity = _cache_identity(document)

    # Check for existing READY shadow artifact (immutable).
    existing = RenderedDocumentArtifact.objects.filter(
        document_id=identity["document_id"],
        revision=identity["revision"],
        payload_hash=identity["payload_hash"],
        engine="qde",
        render_role="shadow",
        status=RenderedDocumentArtifact.Status.READY,
    ).first()
    if existing is not None:
        pdf_bytes = _read_artifact_pdf(existing)
        if pdf_bytes:
            return RenderedDocumentResult(artifact=existing, pdf_bytes=pdf_bytes, cache_hit=True)
        # PDF file missing/corrupt — fall through to re-render.

    # --- QDE render ---
    try:
        qde_result = render_via_qde(document)
    except Exception as exc:
        logger.warning(
            "shadow_qde_render_failed",
            document_id=identity["document_id"],
            error=str(exc),
        )
        return None

    pdf_bytes = qde_result.pdf_bytes
    if not pdf_bytes:
        logger.warning(
            "shadow_qde_empty_output",
            document_id=identity["document_id"],
        )
        return None

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    # --- Build QDE identity axes ---
    template_map = getattr(settings, "DOCUMENT_TEMPLATE_MAP", {})
    document_type = str(document.get("document_type") or "waybill")
    try:
        template_id, template_version = template_map[document_type]
    except (KeyError, TypeError):
        template_id, template_version = "unknown", "0.0.0"

    # --- Persist shadow artifact ---
    try:
        artifact, created = RenderedDocumentArtifact.objects.get_or_create(
            document_id=identity["document_id"],
            revision=identity["revision"],
            payload_hash=identity["payload_hash"],
            document_contract=getattr(settings, "QDE_DOCUMENT_CONTRACT", "warehouse.operation-document/v2"),
            template_id=template_id,
            template_version=template_version,
            engine="qde",
            engine_version=QDE_ENGINE_CONTRACT_VERSION,
            backend="typst",
            backend_version="0.15.1",
            defaults={
                "document_type": document_type,
                "renderer_version": identity["renderer_version"],
                "render_role": "shadow",
                "status": RenderedDocumentArtifact.Status.RENDERING,
            },
        )

        if not created and artifact.status == RenderedDocumentArtifact.Status.READY:
            # Already persisted — immutable, don't overwrite.
            pdf_bytes = _read_artifact_pdf(artifact) or b""
            return RenderedDocumentResult(artifact=artifact, pdf_bytes=pdf_bytes, cache_hit=True)

        # Save PDF file to shadow storage (separate from legacy).
        filename = f"documents/pdf/shadow/{identity['document_id']}_{identity['payload_hash']}.pdf"
        artifact.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)

        artifact.status = RenderedDocumentArtifact.Status.READY
        artifact.pdf_sha256 = pdf_sha256
        artifact.size_bytes = len(pdf_bytes)
        artifact.rendered_at = timezone.now()
        artifact.last_error = ""
        artifact.save(update_fields=[
            "status", "pdf_sha256", "size_bytes", "rendered_at",
            "last_error", "pdf_file", "updated_at",
        ])

        return RenderedDocumentResult(artifact=artifact, pdf_bytes=pdf_bytes, cache_hit=False)

    except Exception as exc:
        logger.warning(
            "shadow_persistence_failed",
            document_id=identity["document_id"],
            error=str(exc),
        )
        return None


def _read_artifact_pdf(artifact: RenderedDocumentArtifact) -> bytes | None:
    """Read PDF bytes from artifact's file field. Returns None on failure."""
    try:
        if artifact.pdf_file:
            return artifact.pdf_file.read()
    except Exception:
        pass
    return None


_MEDIA_BOX_TOLERANCE_PT = 0.1  # 0.1 pt ≈ 0.035 mm — sub-pixel rounding tolerance


def _media_box_equivalent(mb_a: list[float], mb_b: list[float], *, tol: float = _MEDIA_BOX_TOLERANCE_PT) -> bool:
    """Return True if two MediaBox values represent the same physical page geometry.

    Different PDF engines may round coordinate values at different precision.
    A tolerance of 0.1 pt is far below the threshold of any visible difference
    (1 pt ≈ 0.35 mm, so 0.1 pt ≈ 0.035 mm).
    """
    if len(mb_a) != len(mb_b):
        return False
    return all(abs(a - b) <= tol for a, b in zip(mb_a, mb_b))


def compare_pdf_structural(pdf_a: bytes, pdf_b: bytes) -> dict[str, Any]:
    """Compare two PDFs structurally: page count, media box, sha256.

    Uses pypdf for PDF inspection. If pypdf is unavailable, returns
    sha-only comparison with page_count_match/media_box_match = None.

    MediaBox comparison uses a tolerance of 0.1 pt to handle sub-pixel
    rounding differences between Typst and WeasyPrint engines.
    """
    result: dict[str, Any] = {
        "legacy_sha256": hashlib.sha256(pdf_a).hexdigest(),
        "shadow_sha256": hashlib.sha256(pdf_b).hexdigest(),
    }
    result["sha_match"] = result["legacy_sha256"] == result["shadow_sha256"]

    try:
        from pypdf import PdfReader

        reader_a = PdfReader(io.BytesIO(pdf_a))
        reader_b = PdfReader(io.BytesIO(pdf_b))

        result["legacy_page_count"] = len(reader_a.pages)
        result["shadow_page_count"] = len(reader_b.pages)
        result["page_count_match"] = result["legacy_page_count"] == result["shadow_page_count"]

        # Media box comparison (first page) with tolerance.
        if reader_a.pages and reader_b.pages:
            mb_a = [float(v) for v in reader_a.pages[0].mediabox]
            mb_b = [float(v) for v in reader_b.pages[0].mediabox]
            result["legacy_media_box"] = mb_a
            result["shadow_media_box"] = mb_b
            result["media_box_match"] = _media_box_equivalent(mb_a, mb_b)
        else:
            result["legacy_media_box"] = None
            result["shadow_media_box"] = None
            result["media_box_match"] = False
    except ImportError:
        result["legacy_page_count"] = None
        result["shadow_page_count"] = None
        result["page_count_match"] = None
        result["legacy_media_box"] = None
        result["shadow_media_box"] = None
        result["media_box_match"] = None
    except Exception as exc:
        result["legacy_page_count"] = None
        result["shadow_page_count"] = None
        result["page_count_match"] = None
        result["legacy_media_box"] = None
        result["shadow_media_box"] = None
        result["media_box_match"] = None
        result["error"] = str(exc)

    return result
