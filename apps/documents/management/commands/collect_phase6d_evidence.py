"""Collect Phase 6D evidence: render-time legacy-vs-QDE comparison for waybills.

READ-ONLY with respect to domain data. Creates shadow artifacts (allowed).
Writes versioned evidence under spike-out/waybill-qde-vs-django/.

Phase 6D prerequisite fixes baked into this command:

- Corpus comes from SyncServer ``GET /documents`` (no trailing slash), filtered
  by ``document_type`` and paginated with offset/limit. There is no silent
  shadow-artifact fallback: a failed fetch aborts the run.
- Every row records expected AND actual render identity axes, and the run
  manifest records git SHA, settings snapshot and timestamp, so the evidence
  itself proves which template/engine/backend versions produced it.
- Text/content is verified against PDF text extracted from BOTH sides (pypdf)
  with quantity normalization, item-name loss/duplication detection, totals
  markers and empty-page detection.
- ``pages_match`` is a DIAGNOSTIC metric only: template 2.2.0 intentionally
  rebalances pagination, so the legacy >= 95% exact-match gate is not applied
  by this collector.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.documents.services import (
    QDE_ENGINE_CONTRACT_VERSION,
    QDE_SHADOW_BACKEND,
    QDE_SHADOW_BACKEND_VERSION,
    QDE_SHADOW_ENGINE,
    _qde_shadow_identity,
    compare_pdf_structural,
    render_document_pdf,
    render_shadow_pdf,
)
from apps.sync_client.documents_api import DocumentsAPI

try:  # pragma: no cover - import guard only
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment]


MIN_SMALL_CORPUS_GUARD = 50
DEFAULT_EXPECT_TEMPLATE_VERSION = "2.2.0"
SYNC_DOCUMENTS_PATH = "/documents"
SYNC_DOCUMENTS_PAGE_LIMIT = 1000

# Render identity axes that must be present on both sides (expected vs actual).
IDENTITY_AXIS_FIELDS = (
    "template_id",
    "template_version",
    "document_contract",
    "engine",
    "engine_version",
    "backend",
    "backend_version",
)

# Canonical, uniform row schema for JSON and CSV outputs.
RESULT_FIELDS: tuple[str, ...] = (
    "document_id",
    "revision",
    "document_number",
    "document_type",
    "payload_hash_prefix",
    "expected_template_id",
    "expected_template_version",
    "expected_engine",
    "expected_engine_version",
    "expected_backend",
    "expected_backend_version",
    "expected_document_contract",
    "actual_template_id",
    "actual_template_version",
    "actual_engine",
    "actual_engine_version",
    "actual_backend",
    "actual_backend_version",
    "actual_document_contract",
    "identity_violation",
    "legacy_artifact_id",
    "shadow_artifact_id",
    "legacy_sha256",
    "qde_sha256",
    "sha_equal",
    "legacy_pages",
    "qde_pages",
    "pages_match",
    "pages_delta",
    "legacy_media_box",
    "qde_media_box",
    "media_box_match",
    "text_match",
    "missing_required_values",
    "items_unverified",
    "item_loss_count",
    "item_duplication_count",
    "legacy_item_count",
    "qde_item_count",
    "legacy_empty_pages",
    "qde_empty_pages",
    "totals_missing",
    "cache_hit",
    "legacy_cache_hit",
    "verdict",
    "review_reasons",
    "review_primary_reason",
    "legacy_duration_ms",
    "qde_duration_ms",
    "comparison_duration_ms",
    "total_shadow_duration_ms",
    "error",
)

# Priority order for the single primary review reason (content defects first,
# expected pagination differences last).
REVIEW_REASON_PRIORITY = (
    "IDENTITY_VIOLATION",
    "TEXT_EXTRACTION_FAILED",
    "TEXT_REQUIRED_MISSING",
    "ITEM_DUPLICATION",
    "TOTALS_MISSING",
    "EMPTY_PAGE",
    "MEDIA_BOX_DIFF",
    "PAGE_COUNT_DIFF",
    "TEXT_UNVERIFIED",
)

TOTALS_MARKERS = ("Итого", "Всего")


def _normalize_text(value: str) -> str:
    """Normalize whitespace and NBSP for comparison."""
    return re.sub(r"[\s\u00a0]+", " ", value.strip())


def _compact_text(value: str) -> str:
    """Remove all whitespace so line wraps cannot break value matching.

    PDF text extraction inserts whitespace at visual line wraps ("гусь-\\n
    хрустальный", "401107-00323/\\nA,"), so exact substring comparison must be
    whitespace-insensitive.
    """
    return re.sub(r"[\s\u00a0]+", "", value)


def _extract_required_text(document: dict[str, Any]) -> dict[str, Any]:
    """Extract mandatory text values and per-line anchors from canonical contract."""
    payload = document.get("payload") or {}
    operation = payload.get("operation") if isinstance(payload.get("operation"), dict) else {}

    operation_display_number = payload.get("operation_display_number") or operation.get("display_number")

    lines = payload.get("lines") or []
    line_items: list[dict[str, str]] = []
    item_names: list[str] = []
    quantities: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        name = _normalize_text(str(line.get("item_name") or ""))
        unit = _normalize_text(
            str(line.get("unit_symbol") or line.get("unit_name") or line.get("unit_symbol_snapshot") or "")
        )
        quantity = str(line.get("quantity")) if line.get("quantity") is not None else ""
        line_items.append({"name": name, "unit": unit, "quantity": quantity})
        if name:
            item_names.append(name)
        if quantity:
            quantities.append(quantity)

    return {
        "document_number": document.get("document_number"),
        "operation_display_number": str(operation_display_number) if operation_display_number else None,
        "item_names": "|".join(item_names) if item_names else None,
        "quantities": "|".join(quantities) if quantities else None,
        "lines": line_items,
    }


def _quantity_variants(raw: str) -> list[str]:
    """Return printable variants of a quantity value (1.0 -> 1, 1.0, 1,0)."""
    value = str(raw).strip()
    variants = {value} if value else set()
    try:
        number = float(value)
    except ValueError:
        return sorted(variants)
    if number == int(number):
        variants.add(str(int(number)))
    for template in ("{:.1f}", "{:.2f}", "{:.3f}", "{:.4f}"):
        trimmed = template.format(number).rstrip("0").rstrip(".")
        if trimmed:
            variants.add(trimmed)
    for item in list(variants):
        variants.add(item.replace(".", ","))
    for item in list(variants):
        if item.startswith("-"):
            variants.add("\u2212" + item[1:])  # U+2212 minus sign as rendered by Typst
    return sorted(v for v in variants if v)


def _count_anchored_occurrences(text: str, pattern: str) -> int:
    """Count occurrences not glued to a word char before or digits/separators after.

    The leading word boundary prevents short units ("т 2") from matching a word
    tail ("агрегат 2").
    """
    return len(re.findall(r"(?<![\w])" + re.escape(pattern) + r"(?![\d.,])", text))


def _count_numeric_occurrences(text: str, needle: str) -> int:
    """Count numeric-token occurrences, ignoring digits glued to the token."""
    pattern = r"(?<![\d])" + re.escape(needle) + r"(?![\d])"
    return len(re.findall(pattern, text))


def _check_required_values(document: dict[str, Any], legacy_text: str, qde_text: str) -> dict[str, Any]:
    """Differential content check: anything printed by legacy must be in QDE.

    Returns a dict with loss lists, duplication counts and unverified values.
    Internal ``document_number`` is only checked when the legacy PDF prints it
    (the printed number is usually ``operation_display_number``).
    """
    required = _extract_required_text(document)
    losses: list[str] = []
    unverified: list[str] = []
    legacy_compact = _compact_text(legacy_text)
    qde_compact = _compact_text(qde_text)

    # Internal number: differential only — templates are not required to print it.
    document_number = required.get("document_number")
    if document_number:
        compact_number = _compact_text(document_number)
        if compact_number in legacy_compact and compact_number not in qde_compact:
            losses.append(f"document_number:{document_number}")

    display_number = required.get("operation_display_number")
    if display_number:
        compact_display = _compact_text(display_number)
        in_legacy = compact_display in legacy_compact
        in_qde = compact_display in qde_compact
        if in_legacy and not in_qde:
            losses.append(f"operation_display_number:{display_number}")
        elif not in_legacy and not in_qde:
            unverified.append(f"operation_display_number:{display_number}")

    item_loss_count = 0
    item_duplication_count = 0
    legacy_item_count = 0
    qde_item_count = 0
    lines = required.get("lines") or []
    names = [line["name"] for line in lines if line["name"]]
    for name in dict.fromkeys(names):
        compact_name = _compact_text(name)
        if len(compact_name) < 3:
            continue
        legacy_count = legacy_compact.count(compact_name)
        qde_count = qde_compact.count(compact_name)
        legacy_item_count += legacy_count
        qde_item_count += qde_count
        if qde_count < legacy_count:
            item_loss_count += legacy_count - qde_count
            losses.append(f"item:{name}")
        elif qde_count > legacy_count:
            item_duplication_count += qde_count - legacy_count
        elif legacy_count == 0:
            unverified.append(f"item:{name}")

    # Quantities are anchored to their unit ("шт 1", "кг 2") so page counters
    # ("Лист 1 из 2") and row numbers cannot be mistaken for quantities.
    for line in lines:
        raw_quantity = line["quantity"]
        if not raw_quantity:
            continue
        unit = line["unit"]
        variants = _quantity_variants(raw_quantity)
        patterns = [f"{unit} {variant}" for variant in variants] if unit else variants
        if unit:
            legacy_count = max((_count_anchored_occurrences(legacy_text, p) for p in patterns), default=0)
            qde_count = max((_count_anchored_occurrences(qde_text, p) for p in patterns), default=0)
        else:
            legacy_count = max((_count_numeric_occurrences(legacy_text, p) for p in patterns), default=0)
            qde_count = max((_count_numeric_occurrences(qde_text, p) for p in patterns), default=0)
        if legacy_count and qde_count < legacy_count:
            losses.append(f"quantity:{raw_quantity}")
        elif not legacy_count and not qde_count:
            unverified.append(f"quantity:{raw_quantity}")

    legacy_has_totals = any(marker in legacy_text for marker in TOTALS_MARKERS)
    qde_has_totals = any(marker in qde_text for marker in TOTALS_MARKERS)
    totals_missing = bool(legacy_has_totals and not qde_has_totals)

    return {
        "value_losses": losses,
        "unverified": unverified,
        "item_loss_count": item_loss_count,
        "item_duplication_count": item_duplication_count,
        "legacy_item_count": legacy_item_count,
        "qde_item_count": qde_item_count,
        "totals_missing": totals_missing,
    }


def _extract_pdf_text(pdf_bytes: bytes) -> tuple[str, int, int]:
    """Extract normalized text, page count and empty-page count from a PDF."""
    if PdfReader is None:
        raise RuntimeError("pypdf is required for Phase 6D text verification")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_texts = [(page.extract_text() or "") for page in reader.pages]
    empty_pages = sum(1 for text in page_texts if not text.strip())
    return _normalize_text("\n".join(page_texts)), len(page_texts), empty_pages


def _classify_row(
    *,
    pages_match: bool | None,
    media_box_match: bool | None,
    item_loss_count: int,
    item_duplication_count: int,
    value_losses: list[str],
    unverified: list[str],
    totals_missing: bool,
    legacy_empty_pages: int | None,
    qde_empty_pages: int | None,
    identity_violation: str,
    extraction_error: str,
) -> tuple[list[str], str, str]:
    """Classify a comparable row into (reasons, verdict, primary_reason)."""
    reasons: list[str] = []
    if identity_violation:
        reasons.append("IDENTITY_VIOLATION")
    if extraction_error:
        reasons.append("TEXT_EXTRACTION_FAILED")
    if value_losses or item_loss_count:
        reasons.append("TEXT_REQUIRED_MISSING")
    if item_duplication_count:
        reasons.append("ITEM_DUPLICATION")
    if totals_missing:
        reasons.append("TOTALS_MISSING")
    if (
        qde_empty_pages is not None
        and legacy_empty_pages is not None
        and qde_empty_pages > legacy_empty_pages
    ):
        reasons.append("EMPTY_PAGE")
    if not media_box_match:
        reasons.append("MEDIA_BOX_DIFF")
    if not pages_match:
        reasons.append("PAGE_COUNT_DIFF")
    if unverified:
        reasons.append("TEXT_UNVERIFIED")

    if not reasons:
        verdict = "MATCH"
    elif reasons == ["MEDIA_BOX_DIFF"]:
        verdict = "MISMATCH"
    else:
        verdict = "REVIEW_REQUIRED"

    primary = next((reason for reason in REVIEW_REASON_PRIORITY if reason in reasons), "")
    return reasons, verdict, primary


def _blank_result(document_id: str, **overrides: Any) -> dict[str, Any]:
    """Build a row with the complete canonical schema."""
    row: dict[str, Any] = {field: "" for field in RESULT_FIELDS}
    row.update(
        document_id=document_id,
        revision=0,
        payload_hash_prefix="",
        sha_equal=False,
        pages_match=None,
        media_box_match=None,
        text_match=None,
        item_loss_count=0,
        item_duplication_count=0,
        legacy_item_count=0,
        qde_item_count=0,
        legacy_empty_pages=None,
        qde_empty_pages=None,
        totals_missing=False,
        cache_hit=None,
        legacy_cache_hit=None,
        legacy_duration_ms=0,
        qde_duration_ms=0,
        comparison_duration_ms=0,
        total_shadow_duration_ms=0,
        verdict="",
        review_reasons="",
        review_primary_reason="",
        error="",
    )
    row.update(overrides)
    return row


def _identity_axes(document_type: str) -> dict[str, str]:
    """Resolve expected QDE shadow render axes from settings only."""
    template_map = getattr(settings, "DOCUMENT_TEMPLATE_MAP", {})
    try:
        template_id, template_version = template_map[document_type]
    except (KeyError, TypeError):
        template_id, template_version = "unknown", "0.0.0"
    return {
        "template_id": template_id,
        "template_version": template_version,
        "document_contract": getattr(settings, "QDE_DOCUMENT_CONTRACT", "warehouse.operation-document/v2"),
        "engine": QDE_SHADOW_ENGINE,
        "engine_version": QDE_ENGINE_CONTRACT_VERSION,
        "backend": QDE_SHADOW_BACKEND,
        "backend_version": QDE_SHADOW_BACKEND_VERSION,
    }


def _settings_snapshot() -> dict[str, Any]:
    """JSON-safe snapshot of render-relevant settings."""
    template_map = getattr(settings, "DOCUMENT_TEMPLATE_MAP", {}) or {}
    return {
        "DOCUMENTS_RENDER_MODE": getattr(settings, "DOCUMENTS_RENDER_MODE", None),
        "DOCUMENT_TEMPLATE_MAP": {key: list(value) for key, value in template_map.items()},
        "QDE_DOCUMENT_CONTRACT": getattr(settings, "QDE_DOCUMENT_CONTRACT", None),
        "QDE_ENGINE_CONTRACT_VERSION": QDE_ENGINE_CONTRACT_VERSION,
        "QDE_SHADOW_ENGINE": QDE_SHADOW_ENGINE,
        "QDE_SHADOW_BACKEND": QDE_SHADOW_BACKEND,
        "QDE_SHADOW_BACKEND_VERSION": QDE_SHADOW_BACKEND_VERSION,
        "QDE_SUBPROCESS_TIMEOUT_SECONDS": getattr(settings, "QDE_SUBPROCESS_TIMEOUT_SECONDS", None),
    }


def _read_git_sha_from_files(base_dir: str) -> tuple[str, str]:
    """Read HEAD revision/branch from .git files (container without git binary)."""
    git_dir = os.path.join(base_dir, ".git")
    if os.path.isfile(git_dir):  # worktree: ".git" is a file containing "gitdir: ..."
        try:
            with open(git_dir, encoding="utf-8") as handle:
                pointer = handle.read().strip()
        except OSError:
            return "", ""
        if pointer.startswith("gitdir:"):
            git_dir = os.path.normpath(os.path.join(base_dir, pointer.split("gitdir:", 1)[1].strip()))
    head_path = os.path.join(git_dir, "HEAD")
    if not os.path.isfile(head_path):
        return "", ""
    try:
        with open(head_path, encoding="utf-8") as handle:
            head = handle.read().strip()
    except OSError:
        return "", ""
    if not head.startswith("ref:"):
        return head, "detached"
    ref = head.split(":", 1)[1].strip()
    branch = ref.rsplit("/", 1)[-1]
    ref_path = os.path.join(git_dir, ref)
    if os.path.isfile(ref_path):
        with open(ref_path, encoding="utf-8") as handle:
            return handle.read().strip(), branch
    packed_path = os.path.join(git_dir, "packed-refs")
    if os.path.isfile(packed_path):
        with open(packed_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith(("#", "^")) and line.endswith(" " + ref):
                    return line.split(" ", 1)[0], branch
    return "", branch


def _git_info() -> dict[str, Any]:
    """Git revision info of the running Warehouse_web checkout."""
    base_dir = str(getattr(settings, "BASE_DIR", "."))

    def _run(args: list[str]) -> str:
        completed = subprocess.run(
            args,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    try:
        return {
            "git_sha": _run(["git", "rev-parse", "HEAD"]),
            "git_branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
            "git_dirty": bool(_run(["git", "status", "--porcelain"])),
            "git_source": "subprocess",
        }
    except Exception as exc:  # noqa: BLE001 — git info is best-effort; failures are recorded
        sha, branch = _read_git_sha_from_files(base_dir)
        return {
            "git_sha": sha,
            "git_branch": branch,
            "git_dirty": None,
            "git_source": "filesystem",
            "git_error": str(exc),
        }


def _load_document_ids(path: str) -> set[str]:
    """Load document ids from ``path`` (JSON array or one id per line).

    Used by ``--document-ids-file`` for targeted reruns of known
    failures. Blank lines are ignored; ids are stripped.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        raise CommandError(f"Cannot read --document-ids-file {path!r}: {exc}") from exc

    text = raw.strip()
    if text.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in --document-ids-file {path!r}: {exc}") from exc
        if not isinstance(payload, list):
            raise CommandError(f"--document-ids-file {path!r} must contain an array of ids.")
        ids = [str(item).strip() for item in payload]
    else:
        ids = [line.strip().strip(",").strip() for line in text.splitlines()]
    return {item for item in ids if item}


def _build_summary(
    results: list[dict[str, Any]],
    *,
    corpus: dict[str, Any],
    expected_axes: dict[str, str],
    expect_template_version: str,
) -> dict[str, Any]:
    """Aggregate evidence rows. ``pages_match_ratio`` is diagnostic only."""
    distinct_docs = len({row["document_id"] for row in results})
    distinct_revs = len({(row["document_id"], row["revision"]) for row in results})
    match_count = sum(1 for row in results if row["verdict"] == "MATCH")
    review_count = sum(1 for row in results if row["verdict"] == "REVIEW_REQUIRED")
    mismatch_count = sum(1 for row in results if row["verdict"] == "MISMATCH")
    failure_count = sum(
        1 for row in results if row["verdict"] in ("QDE_FAILED", "QDE_EXCEPTION", "LEGACY_FAILED", "FETCH_FAILED")
    )
    comparable = [row for row in results if row["verdict"] in ("MATCH", "MISMATCH", "REVIEW_REQUIRED")]

    pages_match_count = sum(1 for row in comparable if row["pages_match"])
    text_match_count = sum(1 for row in comparable if row["text_match"])
    media_match_count = sum(1 for row in comparable if row["media_box_match"])
    sha_equal_count = sum(1 for row in comparable if row["sha_equal"])
    comparable_count = len(comparable)

    review_reasons: dict[str, int] = {}
    review_primary: dict[str, int] = {}
    pages_delta: dict[str, int] = {}
    for row in comparable:
        for reason in str(row["review_reasons"] or "").split("|"):
            if reason:
                review_reasons[reason] = review_reasons.get(reason, 0) + 1
        if row["review_primary_reason"]:
            key = str(row["review_primary_reason"])
            review_primary[key] = review_primary.get(key, 0) + 1
        if row["pages_delta"] is not None and row["pages_delta"] != "":
            key = str(row["pages_delta"])
            pages_delta[key] = pages_delta.get(key, 0) + 1

    actual_template_versions: dict[str, int] = {}
    identity_violations: list[str] = []
    for row in results:
        version = str(row.get("actual_template_version") or "")
        if version:
            actual_template_versions[version] = actual_template_versions.get(version, 0) + 1
        if row["identity_violation"] or (version and version != expect_template_version):
            identity_violations.append(str(row["document_id"]))

    summary: dict[str, Any] = {
        "total_runs": len(results),
        "distinct_document_id": distinct_docs,
        "distinct_document_revision": distinct_revs,
        "match": match_count,
        "review_required": review_count,
        "mismatch": mismatch_count,
        "qde_failures": failure_count,
        "comparable": comparable_count,
        "pages_match": f"{pages_match_count}/{comparable_count}",
        "pages_match_ratio": f"{pages_match_count / comparable_count * 100:.1f}%" if comparable_count else "N/A",
        "pages_match_note": "diagnostic only; template 2.2.0 intentionally rebalances pagination",
        "text_match": f"{text_match_count}/{comparable_count}",
        "text_match_ratio": f"{text_match_count / comparable_count * 100:.1f}%" if comparable_count else "N/A",
        "media_box_match": f"{media_match_count}/{comparable_count}",
        "media_box_match_ratio": f"{media_match_count / comparable_count * 100:.1f}%" if comparable_count else "N/A",
        "sha_equal": f"{sha_equal_count}/{comparable_count}",
        "sha_equal_ratio": f"{sha_equal_count / comparable_count * 100:.1f}%" if comparable_count else "N/A",
        "corpus": corpus,
        "expected_render_identity": expected_axes,
        "actual_template_version_counts": actual_template_versions,
        "cache_hits": sum(1 for row in results if row["cache_hit"] is True),
        "cache_misses": sum(1 for row in results if row["cache_hit"] is False),
        "legacy_cache_hits": sum(1 for row in results if row["legacy_cache_hit"] is True),
        "review_reasons_distribution": review_reasons,
        "review_primary_distribution": review_primary,
        "pages_delta_distribution": pages_delta,
        "item_loss_rows": sum(1 for row in comparable if row["item_loss_count"]),
        "item_duplication_rows": sum(1 for row in comparable if row["item_duplication_count"]),
        "totals_missing_rows": sum(1 for row in comparable if row["totals_missing"]),
        "empty_page_rows": sum(
            1
            for row in comparable
            if row["qde_empty_pages"] is not None
            and row["legacy_empty_pages"] is not None
            and row["qde_empty_pages"] > row["legacy_empty_pages"]
        ),
        "assertion": {
            "expected_template_version": expect_template_version,
            "all_observed_identities_expected": not identity_violations,
            "violations": identity_violations[:20],
        },
    }

    timings = [row["total_shadow_duration_ms"] for row in comparable if row["total_shadow_duration_ms"]]
    if timings:
        sorted_t = sorted(timings)
        p95_idx = min(int(len(sorted_t) * 0.95), len(sorted_t) - 1)
        summary["latency_ms"] = {
            "min": int(min(timings)),
            "median": int(sorted_t[len(sorted_t) // 2]),
            "p95": int(sorted_t[p95_idx]),
            "max": int(max(timings)),
        }

    return summary


class Command(BaseCommand):
    help = "Collect Phase 6D evidence: render-time legacy-vs-QDE comparison"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max documents to process (0 = all fetched; fetch paginates the whole corpus).",
        )
        parser.add_argument(
            "--corpus-limit",
            type=int,
            default=SYNC_DOCUMENTS_PAGE_LIMIT,
            help="SyncServer page size for corpus fetch (1..1000).",
        )
        parser.add_argument(
            "--document-type",
            type=str,
            default="waybill",
            help="SyncServer document_type filter for the corpus (default: waybill).",
        )
        parser.add_argument(
            "--document-ids-file",
            type=str,
            default="",
            help=(
                "File with document ids to process (JSON array or one per line). "
                "Filters the fetched corpus; used for targeted reruns of known failures."
            ),
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="",
            help="Output directory. Default: versioned spike-out/waybill-qde-vs-django/phase6d-<version>-<UTC>.",
        )
        parser.add_argument(
            "--expect-template-version",
            type=str,
            default=DEFAULT_EXPECT_TEMPLATE_VERSION,
            help="Abort unless DOCUMENT_TEMPLATE_MAP[document_type] has this version.",
        )
        parser.add_argument(
            "--allow-small-corpus",
            action="store_true",
            help=f"Permit a corpus smaller than {MIN_SMALL_CORPUS_GUARD} documents.",
        )
        parser.add_argument(
            "--allow-overwrite-dir",
            action="store_true",
            help="Permit writing into a directory that already holds phase6d evidence.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch corpus and print the plan without rendering or writing evidence.",
        )

    def handle(self, *args, **options):
        limit = int(options["limit"] or 0)
        document_type = options["document_type"]
        page_size = int(options["corpus_limit"] or SYNC_DOCUMENTS_PAGE_LIMIT)
        expect_template_version = options["expect_template_version"]
        allow_small = bool(options["allow_small_corpus"])
        allow_overwrite = bool(options["allow_overwrite_dir"])
        dry_run = bool(options["dry_run"])

        expected_axes = _identity_axes(document_type)
        if expected_axes["template_version"] != expect_template_version:
            raise CommandError(
                "Template version assertion failed: "
                f"DOCUMENT_TEMPLATE_MAP[{document_type!r}] is {expected_axes['template_version']!r}, "
                f"expected {expect_template_version!r}."
            )

        from apps.sync_client.client import SyncServerClient

        client = SyncServerClient(force_root=True)

        self.stdout.write(f"Fetching corpus from SyncServer GET {SYNC_DOCUMENTS_PATH} ...")
        fetched_documents, total_available, pages = self._fetch_documents(
            client, document_type, page_size
        )
        fetched_count = len(fetched_documents)
        documents = fetched_documents
        document_ids_file = options["document_ids_file"]
        if document_ids_file:
            wanted_ids = _load_document_ids(document_ids_file)
            if not wanted_ids:
                raise CommandError(f"--document-ids-file {document_ids_file!r} contains no ids.")
            documents = [
                stub
                for stub in documents
                if (stub.get("id") if isinstance(stub, dict) else str(stub)) in wanted_ids
            ]
            found_ids = {
                (stub.get("id") if isinstance(stub, dict) else str(stub)) for stub in documents
            }
            missing_ids = wanted_ids - found_ids
            if missing_ids:
                raise CommandError(
                    f"--document-ids-file: {len(missing_ids)} id(s) not found in the fetched "
                    f"corpus (first: {sorted(missing_ids)[:3]})."
                )
            self.stdout.write(
                f"Corpus filter: {len(documents)}/{fetched_count} fetched {document_type}(s) "
                f"selected by {document_ids_file}."
            )
        documents = documents[:limit] if limit > 0 else documents
        corpus_size = len(documents)
        self.stdout.write(
            f"Corpus: {corpus_size} to process ({fetched_count} fetched, {total_available} available "
            f"{document_type}(s), {pages} page(s))."
        )

        output_dir = self._resolve_output_dir(options["output_dir"], expected_axes["template_version"])

        if dry_run:
            self._print_dry_run(documents, expected_axes, output_dir, total_available, expect_template_version)
            return

        self._guard_output_dir(output_dir, allow_overwrite)
        if corpus_size < MIN_SMALL_CORPUS_GUARD and not allow_small:
            raise CommandError(
                f"Corpus too small for Phase 6D evidence: {corpus_size} < {MIN_SMALL_CORPUS_GUARD}. "
                "Fix the corpus fetch or pass --allow-small-corpus explicitly."
            )

        api = DocumentsAPI(client)
        results: list[dict[str, Any]] = []

        for index, doc_stub in enumerate(documents):
            doc_id = doc_stub.get("id") if isinstance(doc_stub, dict) else str(doc_stub)
            if not doc_id:
                continue

            self.stdout.write(f"  [{index + 1}/{corpus_size}] {doc_id[:12]}...")

            try:
                document = api.get_document(doc_id)
            except Exception as exc:  # noqa: BLE001 — any fetch failure becomes a FETCH_FAILED row
                self.stdout.write(f"    SKIP: fetch failed: {exc}")
                results.append(self._failure_row(str(doc_id), "FETCH_FAILED", str(exc), expected_axes))
                continue

            identity = _qde_shadow_identity(document)
            expected_row_axes = {f"expected_{key}": str(identity[key]) for key in IDENTITY_AXIS_FIELDS}

            # --- Legacy render (in memory; production cache path) ---
            try:
                legacy_start = time.monotonic()
                legacy_result = render_document_pdf(document)
                legacy_duration = time.monotonic() - legacy_start
                legacy_bytes = legacy_result.pdf_bytes
                legacy_sha = hashlib.sha256(legacy_bytes).hexdigest()
                legacy_artifact_id = legacy_result.artifact.id if legacy_result.artifact else None
                legacy_cache_hit = legacy_result.cache_hit
            except Exception as exc:  # noqa: BLE001 — legacy failures must not abort the corpus run
                self.stdout.write(f"    SKIP: legacy render failed: {exc}")
                results.append(
                    _blank_result(
                        str(doc_id),
                        revision=identity.get("revision", 0),
                        payload_hash_prefix=str(identity.get("payload_hash", ""))[:16],
                        document_number=str(document.get("document_number") or ""),
                        document_type=str(document.get("document_type") or ""),
                        verdict="LEGACY_FAILED",
                        review_reasons="LEGACY_FAILED",
                        review_primary_reason="LEGACY_FAILED",
                        error=str(exc),
                        **expected_row_axes,
                    )
                )
                continue

            # --- Shadow render ---
            shadow_start = time.monotonic()
            try:
                shadow_result = render_shadow_pdf(document)
            except Exception as exc:  # noqa: BLE001 — shadow failures must not abort the corpus run
                shadow_duration = time.monotonic() - shadow_start
                self.stdout.write(f"    SKIP: shadow render exception: {exc}")
                results.append(
                    _blank_result(
                        str(doc_id),
                        revision=identity.get("revision", 0),
                        payload_hash_prefix=str(identity.get("payload_hash", ""))[:16],
                        document_number=str(document.get("document_number") or ""),
                        document_type=str(document.get("document_type") or ""),
                        legacy_artifact_id=legacy_artifact_id,
                        legacy_sha256=legacy_sha,
                        legacy_cache_hit=legacy_cache_hit,
                        legacy_duration_ms=int(legacy_duration * 1000),
                        qde_duration_ms=int(shadow_duration * 1000),
                        verdict="QDE_EXCEPTION",
                        review_reasons="QDE_EXCEPTION",
                        review_primary_reason="QDE_EXCEPTION",
                        error=str(exc),
                        **expected_row_axes,
                    )
                )
                continue
            shadow_duration = time.monotonic() - shadow_start

            if shadow_result is None:
                self.stdout.write("    SKIP: shadow render returned None")
                results.append(
                    _blank_result(
                        str(doc_id),
                        revision=identity.get("revision", 0),
                        payload_hash_prefix=str(identity.get("payload_hash", ""))[:16],
                        document_number=str(document.get("document_number") or ""),
                        document_type=str(document.get("document_type") or ""),
                        legacy_artifact_id=legacy_artifact_id,
                        legacy_sha256=legacy_sha,
                        legacy_cache_hit=legacy_cache_hit,
                        legacy_duration_ms=int(legacy_duration * 1000),
                        qde_duration_ms=int(shadow_duration * 1000),
                        total_shadow_duration_ms=int(shadow_duration * 1000),
                        verdict="QDE_FAILED",
                        review_reasons="QDE_FAILED",
                        review_primary_reason="QDE_FAILED",
                        error="render_shadow_pdf returned None",
                        **expected_row_axes,
                    )
                )
                continue

            shadow_bytes = shadow_result.pdf_bytes
            shadow_sha = hashlib.sha256(shadow_bytes).hexdigest()
            shadow_artifact = shadow_result.artifact
            shadow_artifact_id = shadow_artifact.id if shadow_artifact else None

            actual_row_axes: dict[str, Any] = {}
            identity_violation = ""
            for key in IDENTITY_AXIS_FIELDS:
                actual_value = getattr(shadow_artifact, key, None) if shadow_artifact else None
                actual_row_axes[f"actual_{key}"] = actual_value if actual_value is not None else ""
                expected_value = identity.get(key)
                if expected_value is not None and actual_value is not None and str(actual_value) != str(expected_value):
                    identity_violation += f"{key}: expected={expected_value!r} actual={actual_value!r}; "

            # --- Structural comparison ---
            comparison_start = time.monotonic()
            structural = compare_pdf_structural(legacy_bytes, shadow_bytes)
            comparison_duration = time.monotonic() - comparison_start

            # --- Text / content comparison (in memory, both sides) ---
            extraction_error = ""
            legacy_text = ""
            qde_text = ""
            legacy_empty_pages: int | None = None
            qde_empty_pages: int | None = None
            try:
                legacy_text, _, legacy_empty_pages = _extract_pdf_text(legacy_bytes)
                qde_text, _, qde_empty_pages = _extract_pdf_text(shadow_bytes)
            except Exception as exc:  # noqa: BLE001 — extraction failure is recorded as a review reason
                extraction_error = str(exc)

            if extraction_error:
                content: dict[str, Any] = {
                    "value_losses": [],
                    "unverified": [],
                    "item_loss_count": 0,
                    "item_duplication_count": 0,
                    "legacy_item_count": 0,
                    "qde_item_count": 0,
                    "totals_missing": False,
                }
            else:
                content = _check_required_values(document, legacy_text, qde_text)

            pages_match = structural.get("page_count_match")
            media_box_match = structural.get("media_box_match")

            reasons, verdict, primary_reason = _classify_row(
                pages_match=pages_match,
                media_box_match=media_box_match,
                item_loss_count=content["item_loss_count"],
                item_duplication_count=content["item_duplication_count"],
                value_losses=content["value_losses"],
                unverified=content["unverified"],
                totals_missing=content["totals_missing"],
                legacy_empty_pages=legacy_empty_pages,
                qde_empty_pages=qde_empty_pages,
                identity_violation=identity_violation,
                extraction_error=extraction_error,
            )

            text_match = not (
                content["value_losses"]
                or content["unverified"]
                or content["item_loss_count"]
                or content["item_duplication_count"]
                or content["totals_missing"]
                or extraction_error
            )

            legacy_pages = structural.get("legacy_page_count")
            qde_pages = structural.get("shadow_page_count")
            pages_delta = (
                qde_pages - legacy_pages
                if legacy_pages is not None and qde_pages is not None
                else None
            )

            row = _blank_result(
                str(doc_id),
                revision=identity.get("revision", 0),
                payload_hash_prefix=str(identity.get("payload_hash", ""))[:16],
                document_number=str(document.get("document_number") or ""),
                document_type=str(document.get("document_type") or ""),
                legacy_artifact_id=legacy_artifact_id,
                shadow_artifact_id=shadow_artifact_id,
                legacy_sha256=legacy_sha,
                qde_sha256=shadow_sha,
                sha_equal=structural["sha_match"],
                legacy_pages=legacy_pages,
                qde_pages=qde_pages,
                pages_match=pages_match,
                pages_delta=pages_delta,
                legacy_media_box=structural.get("legacy_media_box"),
                qde_media_box=structural.get("shadow_media_box"),
                media_box_match=media_box_match,
                text_match=text_match,
                missing_required_values="|".join(content["value_losses"]),
                items_unverified="|".join(content["unverified"]),
                item_loss_count=content["item_loss_count"],
                item_duplication_count=content["item_duplication_count"],
                legacy_item_count=content["legacy_item_count"],
                qde_item_count=content["qde_item_count"],
                legacy_empty_pages=legacy_empty_pages,
                qde_empty_pages=qde_empty_pages,
                totals_missing=content["totals_missing"],
                cache_hit=shadow_result.cache_hit,
                legacy_cache_hit=legacy_cache_hit,
                verdict=verdict,
                review_reasons="|".join(reasons),
                review_primary_reason=primary_reason,
                legacy_duration_ms=int(legacy_duration * 1000),
                qde_duration_ms=int(shadow_duration * 1000),
                comparison_duration_ms=int(comparison_duration * 1000),
                total_shadow_duration_ms=int((shadow_duration + comparison_duration) * 1000),
                error=extraction_error,
                **expected_row_axes,
                **actual_row_axes,
                identity_violation=identity_violation,
            )
            results.append(row)

            status_icon = "✓" if verdict == "MATCH" else "✗" if verdict == "MISMATCH" else "?"
            self.stdout.write(
                f"    {status_icon} {verdict} reasons={row['review_reasons'] or '-'} "
                f"pages={pages_match} delta={pages_delta} text={text_match} "
                f"qde={row['qde_duration_ms']}ms cache={row['cache_hit']}"
            )

        corpus = {
            "source": f"SyncServer GET {SYNC_DOCUMENTS_PATH}?document_type={document_type}",
            "document_type": document_type,
            "total_available": total_available,
            "fetched": fetched_count,
            "processed": corpus_size,
            "pages_fetched": pages,
            "limit_applied": limit,
            "document_ids_file": document_ids_file or None,
        }
        summary = _build_summary(
            results,
            corpus=corpus,
            expected_axes=expected_axes,
            expect_template_version=expect_template_version,
        )

        os.makedirs(output_dir, exist_ok=True)

        comparisons_json_path = os.path.join(output_dir, "phase6d-comparisons.json")
        with open(comparisons_json_path, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=False, indent=2, default=str)

        comparisons_csv_path = os.path.join(output_dir, "phase6d-comparisons.csv")
        with open(comparisons_csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(RESULT_FIELDS),
                extrasaction="ignore",
                restval="",
            )
            writer.writeheader()
            writer.writerows(results)

        summary_path = os.path.join(output_dir, "phase6d-summary.json")
        with open(summary_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2, default=str)

        manifest = {
            "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "warehouse_web": _git_info(),
            "settings_snapshot": _settings_snapshot(),
            "expected_render_identity": expected_axes,
            "expected_template_version": expect_template_version,
            "corpus": corpus,
            "observed": {
                "actual_template_version_counts": summary["actual_template_version_counts"],
                "cache_hits": summary["cache_hits"],
                "cache_misses": summary["cache_misses"],
                "legacy_cache_hits": summary["legacy_cache_hits"],
            },
            "assertion": summary["assertion"],
        }
        manifest_path = os.path.join(output_dir, "phase6d-run-manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2, default=str)

        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("PHASE 6D EVIDENCE SUMMARY")
        self.stdout.write("=" * 60)
        for key, value in summary.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write("")
        self.stdout.write(f"Evidence written to: {output_dir}/")
        self.stdout.write(f"  {comparisons_json_path} ({len(results)} records)")
        self.stdout.write(f"  {comparisons_csv_path}")
        self.stdout.write(f"  {summary_path}")
        self.stdout.write(f"  {manifest_path}")

    # ------------------------------------------------------------------ helpers

    def _fetch_documents(
        self,
        client: Any,
        document_type: str,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Fetch the whole corpus via GET /documents with offset pagination."""
        page_size = max(1, min(int(page_size), SYNC_DOCUMENTS_PAGE_LIMIT))
        documents: list[dict[str, Any]] = []
        total: int | None = None
        offset = 0
        pages = 0

        while True:
            response = client.get(
                SYNC_DOCUMENTS_PATH,
                params={"document_type": document_type, "limit": page_size, "offset": offset},
            )
            if not isinstance(response, dict):
                raise CommandError(
                    f"Unexpected SyncServer response type for {SYNC_DOCUMENTS_PATH}: "
                    f"{type(response).__name__}; expected a paginated object."
                )
            items = response.get("items") or []
            if total is None:
                total = int(response.get("total") or 0)
            documents.extend(items)
            pages += 1
            offset += len(items)
            if not items:
                break
            if offset >= total:
                break

        return documents, total, pages

    def _resolve_output_dir(self, output_dir: str, template_version: str) -> str:
        if output_dir:
            return output_dir
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"spike-out/waybill-qde-vs-django/phase6d-{template_version}-{timestamp}"

    def _guard_output_dir(self, output_dir: str, allow_overwrite: bool) -> None:
        summary_path = os.path.join(output_dir, "phase6d-summary.json")
        if os.path.exists(summary_path) and not allow_overwrite:
            raise CommandError(
                f"Refusing to overwrite existing evidence in {output_dir!r}. "
                "Choose another --output-dir or pass --allow-overwrite-dir."
            )

    def _failure_row(
        self,
        document_id: str,
        verdict: str,
        error: str,
        expected_axes: dict[str, str],
    ) -> dict[str, Any]:
        return _blank_result(
            document_id,
            verdict=verdict,
            review_reasons=verdict,
            review_primary_reason=verdict,
            error=error,
            **{f"expected_{key}": value for key, value in expected_axes.items()},
        )

    def _print_dry_run(
        self,
        documents: list[dict[str, Any]],
        expected_axes: dict[str, str],
        output_dir: str,
        total_available: int,
        expect_template_version: str,
    ) -> None:
        self.stdout.write("DRY RUN — no renders, no evidence files.")
        self.stdout.write(f"  expected_render_identity: {expected_axes}")
        self.stdout.write(f"  template_version_assertion: {expected_axes['template_version']} == {expect_template_version}")
        self.stdout.write(f"  total_available: {total_available}")
        self.stdout.write(f"  documents_to_process: {len(documents)}")
        self.stdout.write(f"  planned_output_dir: {output_dir}")
        if len(documents) < MIN_SMALL_CORPUS_GUARD:
            self.stdout.write(
                f"  WARNING: corpus < {MIN_SMALL_CORPUS_GUARD}; a real run needs --allow-small-corpus."
            )
        summary_path = os.path.join(output_dir, "phase6d-summary.json")
        if os.path.exists(summary_path):
            self.stdout.write(f"  WARNING: {output_dir} already holds evidence; a real run needs --allow-overwrite-dir.")
        for doc_stub in documents[:5]:
            doc_id = doc_stub.get("id") if isinstance(doc_stub, dict) else doc_stub
            self.stdout.write(f"  sample: {doc_id}")
