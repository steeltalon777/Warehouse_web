"""Compare legacy vs shadow PDF artifacts for structural differences.

Read-only command: pairs artifacts by (document_id, revision, payload_hash)
where both a legacy and shadow render_role exist for the same document,
then compares their PDF hashes.  Output includes match_ratio and
structural_match_ratio.
"""

from __future__ import annotations

import hashlib

from django.core.management.base import BaseCommand

from apps.documents.models import RenderedDocumentArtifact
from apps.documents.services import compare_pdf_structural


class Command(BaseCommand):
    help = "Compare legacy and shadow PDF artifacts (read-only)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max number of pairs to compare (0 = all).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 0:
            self.stderr.write("--limit must be non-negative")
            return

        legacy_qs = RenderedDocumentArtifact.objects.filter(
            render_role="legacy",
            status=RenderedDocumentArtifact.Status.READY,
        )
        shadow_qs = RenderedDocumentArtifact.objects.filter(
            render_role="shadow",
            status=RenderedDocumentArtifact.Status.READY,
        )

        legacy_by_key: dict[tuple, RenderedDocumentArtifact] = {}
        for artifact in legacy_qs:
            key = (
                artifact.document_id,
                artifact.revision,
                artifact.payload_hash,
            )
            legacy_by_key[key] = artifact

        pairs: list[tuple[RenderedDocumentArtifact, RenderedDocumentArtifact]] = []
        for artifact in shadow_qs:
            key = (
                artifact.document_id,
                artifact.revision,
                artifact.payload_hash,
            )
            if key in legacy_by_key:
                pairs.append((legacy_by_key[key], artifact))

        if limit > 0:
            pairs = pairs[:limit]

        total = len(pairs)
        if total == 0:
            self.stdout.write("No comparable legacy/shadow pairs found.")
            return

        structural_match_count = 0

        for legacy, shadow in pairs:
            legacy_pdf = self._read_pdf(legacy)
            shadow_pdf = self._read_pdf(shadow)

            if legacy_pdf is None or shadow_pdf is None:
                self.stdout.write(
                    f"[SKIP] doc={legacy.document_id} rev={legacy.revision} "
                    f"— missing PDF file"
                )
                continue

            legacy_sha = hashlib.sha256(legacy_pdf).hexdigest()
            shadow_sha = hashlib.sha256(shadow_pdf).hexdigest()
            sha_matches = legacy_sha == shadow_sha

            structural = compare_pdf_structural(legacy_pdf, shadow_pdf)
            structural_matches = structural.get("page_count_match") and structural.get("media_box_match")
            if structural_matches:
                structural_match_count += 1

            # Contract: MATCH if structural (pages + media_box) matches.
            # SHA inequality between different engines is diagnostic only.
            status = "MATCH" if structural_matches else "MISMATCH"
            self.stdout.write(
                f"[{status}] doc={legacy.document_id} rev={legacy.revision} "
                f"legacy_sha={legacy_sha[:12]} shadow_sha={shadow_sha[:12]} "
                f"page_count_match={structural.get('page_count_match')} "
                f"media_box_match={structural.get('media_box_match')}"
            )

        structural_ratio = structural_match_count / total if total else 0.0

        self.stdout.write(
            f"\nTotal pairs: {total}\n"
            f"Structural match ratio: {structural_match_count}/{total} = {structural_ratio:.2%}"
        )

    @staticmethod
    def _read_pdf(artifact: RenderedDocumentArtifact) -> bytes | None:
        try:
            if artifact.pdf_file:
                return artifact.pdf_file.read()
        except Exception:
            pass
        return None
