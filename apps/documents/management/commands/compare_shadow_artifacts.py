"""Compare legacy vs shadow PDF artifacts for structural differences.

Read-only command.

Pairing is identity-exact.  A pair is emitted only when BOTH artifacts
describe the SAME render input and are the CURRENT revision of their
producer:

* shared input identity (must be equal on both sides):
  ``document_id, revision, payload_hash, document_contract``;
* producer identity (resolved per side, never mixed across revisions):
  ``template_id, template_version, engine, engine_version, backend,
  backend_version``.

Legacy rows are selected by the canonical legacy axes
(``DEFAULT_LEGACY_AXES`` + ``settings.DOCUMENT_RENDERER_VERSION``); shadow
rows by the current QDE mapping (``settings.DOCUMENT_TEMPLATE_MAP`` +
``settings.QDE_DOCUMENT_CONTRACT`` + the fixed QDE shadow axes).

Historical render revisions (older template / engine / backend versions)
are counted as skipped and are NEVER paired: a legacy row rendered by
``waybill-pdf-v1`` is not compared against a QDE shadow rendered from the
2.2.1 template, and a 2.2.0 shadow is not selected after the mapping bumps
to 2.2.1.  ``render_role`` and ``status`` are reuse qualifiers, not
identity axes (TZ-QDE_INTEGRATION_READINESS §5.3/§5.5/§6.6).

One deliberate asymmetry: legacy ``template_id``/``template_version`` are
document-provided renderer labels (e.g. ``waybill_v1``) and never equal
the QDE package axes (e.g. ``warehouse-waybill-ru@2.2.1``), so the legacy
label is not a cross-engine pairing axis; the legacy side is pinned by its
engine/backend/contract axes instead.

Output includes match_ratio and structural_match_ratio, plus identity
coverage counts so an operator can see which artifacts were skipped as
non-current or left unpaired.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.documents.models import RenderedDocumentArtifact
from apps.documents.services import (
    DEFAULT_LEGACY_AXES,
    QDE_ARTIFACT_IDENTITY_FIELDS,
    QDE_ENGINE_CONTRACT_VERSION,
    QDE_SHADOW_BACKEND,
    QDE_SHADOW_BACKEND_VERSION,
    QDE_SHADOW_ENGINE,
    compare_pdf_structural,
)

# Shared render input: must be identical on both sides of a valid pair.
INPUT_IDENTITY_FIELDS = (
    "document_id",
    "revision",
    "payload_hash",
    "document_contract",
)

# Producer revision axes: resolved independently per side.  Legacy and QDE
# rows differ here by design; equality is enforced WITHIN a side (against the
# expected axes), never across legacy vs shadow.
PRODUCER_IDENTITY_FIELDS = tuple(
    field for field in QDE_ARTIFACT_IDENTITY_FIELDS if field not in INPUT_IDENTITY_FIELDS
)


def _artifact_input_key(artifact: RenderedDocumentArtifact) -> tuple:
    return tuple(getattr(artifact, field) for field in INPUT_IDENTITY_FIELDS)


def _expected_legacy_axes() -> dict[str, str]:
    """Canonical axes of the CURRENT legacy renderer revision.

    Mirrors ``render_document_pdf``: engine/backend/contract come from
    ``DEFAULT_LEGACY_AXES``, ``engine_version`` from
    ``settings.DOCUMENT_RENDERER_VERSION``.  template_id/template_version are
    document-provided legacy labels and are deliberately not constrained (see
    module docstring).
    """
    return {
        "document_contract": DEFAULT_LEGACY_AXES["document_contract"],
        "engine": DEFAULT_LEGACY_AXES["engine"],
        "engine_version": getattr(
            settings,
            "DOCUMENT_RENDERER_VERSION",
            DEFAULT_LEGACY_AXES["engine_version"],
        ),
        "backend": DEFAULT_LEGACY_AXES["backend"],
        "backend_version": DEFAULT_LEGACY_AXES["backend_version"],
    }


def _expected_shadow_axes(document_type: str) -> dict[str, str]:
    """Axes of the CURRENT QDE shadow revision for a document type.

    Mirrors ``_qde_shadow_identity``: template axes come ONLY from
    ``settings.DOCUMENT_TEMPLATE_MAP``, contract from
    ``settings.QDE_DOCUMENT_CONTRACT``.
    """
    template_map = getattr(settings, "DOCUMENT_TEMPLATE_MAP", {}) or {}
    try:
        template_id, template_version = template_map[document_type]
    except (KeyError, TypeError):
        template_id, template_version = "unknown", "0.0.0"
    return {
        "document_contract": getattr(
            settings,
            "QDE_DOCUMENT_CONTRACT",
            "warehouse.operation-document/v2",
        ),
        "template_id": template_id,
        "template_version": template_version,
        "engine": QDE_SHADOW_ENGINE,
        "engine_version": QDE_ENGINE_CONTRACT_VERSION,
        "backend": QDE_SHADOW_BACKEND,
        "backend_version": QDE_SHADOW_BACKEND_VERSION,
    }


def _matches_expected(
    artifact: RenderedDocumentArtifact, expected: dict[str, str]
) -> bool:
    return all(getattr(artifact, field) == value for field, value in expected.items())


class Command(BaseCommand):
    help = "Compare current legacy and shadow PDF artifacts by full render identity (read-only)"

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

        ready = RenderedDocumentArtifact.objects.filter(
            status=RenderedDocumentArtifact.Status.READY,
        )

        shadow_by_input: dict[tuple, RenderedDocumentArtifact] = {}
        shadow_axes_cache: dict[str, dict[str, str]] = {}
        skipped_shadow = 0
        # Newest row wins deterministically when siblings share the input key
        # (highest id first + setdefault).
        for artifact in ready.filter(render_role="shadow").order_by("-id"):
            expected = shadow_axes_cache.get(artifact.document_type)
            if expected is None:
                expected = _expected_shadow_axes(artifact.document_type)
                shadow_axes_cache[artifact.document_type] = expected
            if not _matches_expected(artifact, expected):
                skipped_shadow += 1
                continue
            shadow_by_input.setdefault(_artifact_input_key(artifact), artifact)

        legacy_expected = _expected_legacy_axes()
        legacy_by_input: dict[tuple, RenderedDocumentArtifact] = {}
        skipped_legacy = 0
        for artifact in ready.filter(render_role="legacy").order_by("-id"):
            if not _matches_expected(artifact, legacy_expected):
                skipped_legacy += 1
                continue
            legacy_by_input.setdefault(_artifact_input_key(artifact), artifact)

        matched_keys = sorted(legacy_by_input.keys() & shadow_by_input.keys())
        matched = [(legacy_by_input[key], shadow_by_input[key]) for key in matched_keys]

        unpaired_legacy = len(legacy_by_input) - len(matched)
        unpaired_shadow = len(shadow_by_input) - len(matched)

        pairs = matched[:limit] if limit > 0 else matched
        total = len(pairs)

        if total == 0:
            self.stdout.write("No comparable legacy/shadow pairs found.")
            self._write_identity_coverage(
                paired=len(matched),
                skipped_legacy=skipped_legacy,
                skipped_shadow=skipped_shadow,
                unpaired_legacy=unpaired_legacy,
                unpaired_shadow=unpaired_shadow,
            )
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
                f"qde_template={shadow.template_id}@{shadow.template_version} "
                f"page_count_match={structural.get('page_count_match')} "
                f"media_box_match={structural.get('media_box_match')}"
            )

        structural_ratio = structural_match_count / total if total else 0.0

        self.stdout.write(
            f"\nTotal pairs: {total}\n"
            f"Structural match ratio: {structural_match_count}/{total} = {structural_ratio:.2%}"
        )
        self._write_identity_coverage(
            paired=len(matched),
            skipped_legacy=skipped_legacy,
            skipped_shadow=skipped_shadow,
            unpaired_legacy=unpaired_legacy,
            unpaired_shadow=unpaired_shadow,
        )

    def _write_identity_coverage(
        self,
        *,
        paired: int,
        skipped_legacy: int,
        skipped_shadow: int,
        unpaired_legacy: int,
        unpaired_shadow: int,
    ) -> None:
        self.stdout.write(
            f"\nIdentity coverage: paired={paired} "
            f"current_legacy={paired + unpaired_legacy} "
            f"current_shadow={paired + unpaired_shadow}\n"
            f"Skipped non-current revisions: legacy={skipped_legacy} shadow={skipped_shadow}\n"
            f"Unpaired current artifacts: legacy={unpaired_legacy} shadow={unpaired_shadow}"
        )

    @staticmethod
    def _read_pdf(artifact: RenderedDocumentArtifact) -> bytes | None:
        try:
            if artifact.pdf_file:
                return artifact.pdf_file.read()
        except Exception:
            pass
        return None
