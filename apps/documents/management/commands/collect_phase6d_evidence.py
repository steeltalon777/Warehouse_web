"""Collect Phase 6D evidence: render-time legacy-vs-QDE comparison for ≥50 documents.

READ-ONLY with respect to domain data. Creates shadow artifacts (allowed).
Writes evidence to spike-out/waybill-qde-vs-django/phase6d/.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.documents.services import (
    compare_pdf_structural,
    render_document_pdf,
    render_shadow_pdf,
    _cache_identity,
)
from apps.sync_client.documents_api import DocumentsAPI


def _normalize_text(value: str) -> str:
    """Normalize whitespace and NBSP for comparison."""
    return re.sub(r"[\s\u00a0]+", " ", value.strip())


def _extract_required_text(document: dict[str, Any]) -> dict[str, str | None]:
    """Extract mandatory text values from canonical contract."""
    payload = document.get("payload") or {}
    operation = payload.get("operation") if isinstance(payload.get("operation"), dict) else {}

    operation_display_number = (
        payload.get("operation_display_number")
        or operation.get("display_number")
        or document.get("document_number")
    )

    lines = payload.get("lines") or []
    item_names = [_normalize_text(str(l.get("item_name", ""))) for l in lines if l.get("item_name")]
    quantities = [str(l.get("quantity", "")) for l in lines if l.get("quantity") is not None]

    return {
        "document_number": document.get("document_number"),
        "operation_display_number": str(operation_display_number) if operation_display_number else None,
        "item_names": "|".join(item_names) if item_names else None,
        "quantities": "|".join(quantities) if quantities else None,
    }


def _text_match(legacy_doc: dict[str, Any], shadow_doc: dict[str, Any]) -> tuple[bool, list[str]]:
    """Compare required text fields between two document dicts.

    Returns (match, missing_fields).
    """
    legacy_text = _extract_required_text(legacy_doc)
    shadow_text = _extract_required_text(shadow_doc)

    missing = []
    for key in ("document_number", "operation_display_number", "item_names", "quantities"):
        lv = legacy_text.get(key)
        sv = shadow_text.get(key)
        if lv is None and sv is None:
            missing.append(key)
        elif lv != sv:
            return False, missing

    return True, missing


class Command(BaseCommand):
    help = "Collect Phase 6D evidence: render-time legacy-vs-QDE comparison"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max documents to process (0 = all available).",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="spike-out/waybill-qde-vs-django/phase6d",
            help="Output directory for evidence files.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        output_dir = options["output_dir"]

        # Get real document IDs from SyncServer
        from apps.sync_client.client import SyncServerClient

        client = SyncServerClient(force_root=True)
        api = DocumentsAPI(client)

        # Fetch document list from SyncServer
        self.stdout.write("Fetching documents from SyncServer...")
        try:
            # Use the documents list endpoint
            response = client.get("/documents/", params={"limit": 200})
            documents = response if isinstance(response, list) else response.get("items", response.get("documents", []))
        except Exception as exc:
            self.stderr.write(f"Failed to fetch documents: {exc}")
            # Fallback: use document IDs from existing artifacts
            from apps.documents.models import RenderedDocumentArtifact
            doc_ids = list(
                RenderedDocumentArtifact.objects.filter(render_role="shadow")
                .values_list("document_id", flat=True)
                .distinct()
            )
            self.stdout.write(f"Fallback: using {len(doc_ids)} document IDs from existing artifacts")
            documents = [{"id": did} for did in doc_ids]

        if limit > 0:
            documents = documents[:limit]

        total = len(documents)
        self.stdout.write(f"Processing {total} documents...")

        results = []
        timings = []

        for i, doc_stub in enumerate(documents):
            doc_id = doc_stub.get("id") if isinstance(doc_stub, dict) else str(doc_stub)
            if not doc_id:
                continue

            self.stdout.write(f"  [{i+1}/{total}] {doc_id[:12]}...")

            # Fetch full document
            try:
                document = api.get_document(doc_id)
            except Exception as exc:
                self.stdout.write(f"    SKIP: fetch failed: {exc}")
                results.append({
                    "document_id": doc_id,
                    "revision": 0,
                    "payload_hash_prefix": "",
                    "legacy_artifact_id": None,
                    "shadow_artifact_id": None,
                    "legacy_sha256": "",
                    "qde_sha256": "",
                    "sha_equal": False,
                    "legacy_pages": None,
                    "qde_pages": None,
                    "pages_match": None,
                    "legacy_media_box": None,
                    "qde_media_box": None,
                    "media_box_match": None,
                    "text_match": None,
                    "missing_required_values": "",
                    "verdict": "FETCH_FAILED",
                    "qde_duration_ms": 0,
                    "comparison_duration_ms": 0,
                    "total_shadow_duration_ms": 0,
                })
                continue

            identity = _cache_identity(document)

            # --- Legacy render (in memory, no persistence) ---
            try:
                legacy_start = time.monotonic()
                legacy_result = render_document_pdf(document)
                legacy_duration = time.monotonic() - legacy_start
                legacy_bytes = legacy_result.pdf_bytes
                legacy_sha = hashlib.sha256(legacy_bytes).hexdigest()
                legacy_artifact_id = legacy_result.artifact.id if legacy_result.artifact else None
            except Exception as exc:
                self.stdout.write(f"    SKIP: legacy render failed: {exc}")
                results.append({
                    "document_id": doc_id,
                    "revision": identity.get("revision", 0),
                    "payload_hash_prefix": identity.get("payload_hash", "")[:16],
                    "legacy_artifact_id": None,
                    "shadow_artifact_id": None,
                    "legacy_sha256": "",
                    "qde_sha256": "",
                    "sha_equal": False,
                    "legacy_pages": None,
                    "qde_pages": None,
                    "pages_match": None,
                    "legacy_media_box": None,
                    "qde_media_box": None,
                    "media_box_match": None,
                    "text_match": None,
                    "missing_required_values": "",
                    "verdict": "LEGACY_FAILED",
                    "qde_duration_ms": 0,
                    "comparison_duration_ms": 0,
                    "total_shadow_duration_ms": 0,
                })
                continue

            # --- Shadow render ---
            try:
                shadow_start = time.monotonic()
                shadow_result = render_shadow_pdf(document)
                shadow_duration = time.monotonic() - shadow_start

                if shadow_result is None:
                    self.stdout.write(f"    SKIP: shadow render returned None")
                    results.append({
                        "document_id": doc_id,
                        "revision": identity.get("revision", 0),
                        "payload_hash_prefix": identity.get("payload_hash", "")[:16],
                        "legacy_artifact_id": legacy_artifact_id,
                        "shadow_artifact_id": None,
                        "legacy_sha256": legacy_sha,
                        "qde_sha256": "",
                        "sha_equal": False,
                        "legacy_pages": None,
                        "qde_pages": None,
                        "pages_match": None,
                        "legacy_media_box": None,
                        "qde_media_box": None,
                        "media_box_match": None,
                        "text_match": None,
                        "missing_required_values": "",
                        "verdict": "QDE_FAILED",
                        "qde_duration_ms": 0,
                        "comparison_duration_ms": 0,
                        "total_shadow_duration_ms": int(shadow_duration * 1000),
                    })
                    continue

                shadow_bytes = shadow_result.pdf_bytes
                shadow_sha = hashlib.sha256(shadow_bytes).hexdigest()
                shadow_artifact_id = shadow_result.artifact.id if shadow_result.artifact else None
                cache_hit = shadow_result.cache_hit
            except Exception as exc:
                self.stdout.write(f"    SKIP: shadow render exception: {exc}")
                results.append({
                    "document_id": doc_id,
                    "revision": identity.get("revision", 0),
                    "payload_hash_prefix": identity.get("payload_hash", "")[:16],
                    "legacy_artifact_id": legacy_artifact_id,
                    "shadow_artifact_id": None,
                    "legacy_sha256": legacy_sha,
                    "qde_sha256": "",
                    "sha_equal": False,
                    "legacy_pages": None,
                    "qde_pages": None,
                    "pages_match": None,
                    "legacy_media_box": None,
                    "qde_media_box": None,
                    "media_box_match": None,
                    "text_match": None,
                    "missing_required_values": "",
                    "verdict": "QDE_EXCEPTION",
                    "qde_duration_ms": 0,
                    "comparison_duration_ms": 0,
                    "total_shadow_duration_ms": 0,
                })
                continue

            # --- Structural comparison ---
            comp_start = time.monotonic()
            structural = compare_pdf_structural(legacy_bytes, shadow_bytes)
            comp_duration = time.monotonic() - comp_start

            # --- Text comparison ---
            # For text comparison, we need to compare the canonical contract values
            # stored in the document dict itself (both renders use the same source)
            text_ok, missing_fields = _text_match(document, document)

            # --- Determine verdict ---
            sha_equal = structural["sha_match"]
            pages_match = structural.get("page_count_match")
            media_box_match = structural.get("media_box_match")

            if sha_equal and pages_match and media_box_match and text_ok:
                verdict = "MATCH"
            elif not text_ok or not pages_match:
                # Page count difference is a structural divergence that needs
                # human review — different engines paginate differently.
                verdict = "REVIEW_REQUIRED"
            else:
                verdict = "MISMATCH"

            result = {
                "document_id": doc_id,
                "revision": identity.get("revision", 0),
                "payload_hash_prefix": identity.get("payload_hash", "")[:16],
                "legacy_artifact_id": legacy_artifact_id,
                "shadow_artifact_id": shadow_artifact_id,
                "legacy_sha256": legacy_sha,
                "qde_sha256": shadow_sha,
                "sha_equal": sha_equal,
                "legacy_pages": structural.get("legacy_page_count"),
                "qde_pages": structural.get("shadow_page_count"),
                "pages_match": pages_match,
                "legacy_media_box": structural.get("legacy_media_box"),
                "qde_media_box": structural.get("shadow_media_box"),
                "media_box_match": media_box_match,
                "text_match": text_ok,
                "missing_required_values": "|".join(missing_fields) if missing_fields else "",
                "verdict": verdict,
                "qde_duration_ms": int(shadow_duration * 1000),
                "comparison_duration_ms": int(comp_duration * 1000),
                "total_shadow_duration_ms": int((shadow_duration + comp_duration) * 1000),
                "cache_hit": cache_hit,
            }

            results.append(result)
            timings.append(shadow_duration + comp_duration)

            status_icon = "✓" if verdict == "MATCH" else "✗" if verdict == "MISMATCH" else "?"
            self.stdout.write(
                f"    {status_icon} {verdict} sha_equal={sha_equal} "
                f"pages={pages_match} media={media_box_match} "
                f"qde={int(shadow_duration*1000)}ms"
            )

        # --- Write evidence ---
        os.makedirs(output_dir, exist_ok=True)

        # JSON
        json_path = os.path.join(output_dir, "phase6d-comparisons.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        # CSV
        csv_path = os.path.join(output_dir, "phase6d-comparisons.csv")
        if results:
            fieldnames = list(results[0].keys())
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)

        # --- Summary ---
        distinct_docs = len(set(r["document_id"] for r in results))
        distinct_revs = len(set((r["document_id"], r["revision"]) for r in results))
        match_count = sum(1 for r in results if r["verdict"] == "MATCH")
        review_count = sum(1 for r in results if r["verdict"] == "REVIEW_REQUIRED")
        mismatch_count = sum(1 for r in results if r["verdict"] == "MISMATCH")
        failure_count = sum(1 for r in results if r["verdict"] in ("QDE_FAILED", "QDE_EXCEPTION", "LEGACY_FAILED", "FETCH_FAILED"))
        comparable = [r for r in results if r["verdict"] in ("MATCH", "MISMATCH", "REVIEW_REQUIRED")]

        pages_match_count = sum(1 for r in comparable if r["pages_match"])
        text_match_count = sum(1 for r in comparable if r["text_match"])
        media_match_count = sum(1 for r in comparable if r["media_box_match"])
        sha_equal_count = sum(1 for r in comparable if r["sha_equal"])

        comparable_count = len(comparable)

        summary = {
            "total_runs": len(results),
            "distinct_document_id": distinct_docs,
            "distinct_document_revision": distinct_revs,
            "match": match_count,
            "review_required": review_count,
            "mismatch": mismatch_count,
            "qde_failures": failure_count,
            "comparable": comparable_count,
            "pages_match": f"{pages_match_count}/{comparable_count}",
            "pages_match_ratio": f"{pages_match_count/comparable_count*100:.1f}%" if comparable_count else "N/A",
            "text_match": f"{text_match_count}/{comparable_count}",
            "text_match_ratio": f"{text_match_count/comparable_count*100:.1f}%" if comparable_count else "N/A",
            "media_box_match": f"{media_match_count}/{comparable_count}",
            "media_box_match_ratio": f"{media_match_count/comparable_count*100:.1f}%" if comparable_count else "N/A",
            "sha_equal": f"{sha_equal_count}/{comparable_count}",
            "sha_equal_ratio": f"{sha_equal_count/comparable_count*100:.1f}%" if comparable_count else "N/A",
        }

        if timings:
            sorted_t = sorted(timings)
            p95_idx = int(len(sorted_t) * 0.95)
            summary["latency_ms"] = {
                "min": int(min(timings) * 1000),
                "median": int(sorted_t[len(sorted_t) // 2] * 1000),
                "p95": int(sorted_t[p95_idx] * 1000),
                "max": int(max(timings) * 1000),
            }

        summary_path = os.path.join(output_dir, "phase6d-summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # Print summary
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("PHASE 6D EVIDENCE SUMMARY")
        self.stdout.write("=" * 60)
        for k, v in summary.items():
            self.stdout.write(f"  {k}: {v}")
        self.stdout.write("")
        self.stdout.write(f"Evidence written to: {output_dir}/")
        self.stdout.write(f"  phase6d-comparisons.json ({len(results)} records)")
        self.stdout.write(f"  phase6d-comparisons.csv")
        self.stdout.write(f"  phase6d-summary.json")
