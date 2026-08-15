"""Migration 0002 roundtrip tests (TZ-QDE_INTEGRATION_READINESS §5.6, §10).

Runs the real Django migration executor against the test database:

    0001 -> 0002 -> 0001 -> 0002

with production-like legacy rows created on the 0001 schema. Verifies that
legacy business/artifact data survives forward, backward and second forward
migrations without loss.
"""

from __future__ import annotations

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

_APP = "documents"
_MIGRATION_0001 = "0001_initial"
_MIGRATION_0002 = "0002_rendered_document_artifact_v2"

# Same canonical values as the migration itself (self-contained; do not import
# runtime settings/model code here).
LEGACY_DEFAULTS = {
    "engine": "django-legacy",
    "engine_version_fallback": "waybill-pdf-v3",
    "backend": "weasyprint",
    "backend_version": "66.0",
    "document_contract": "warehouse.operation-document/v2",
    "layout_version": "layout-v7.1",
    "render_role": "legacy",
}


def _executor() -> MigrationExecutor:
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    return executor


def _migrate(target: str) -> MigrationExecutor:
    executor = _executor()
    executor.migrate([(_APP, target)])
    return executor


def _app_models(executor: MigrationExecutor, target: str):
    return executor.loader.project_state([(_APP, target)]).apps


def _create_legacy_rows(apps) -> list[dict]:
    """Create production-like legacy rows on the 0001 schema.

    Rows differ in renderer_version (set vs empty), template_version,
    status (READY/FAILED), pdf metadata, payload_hash and revision.
    """
    Artifact = apps.get_model(_APP, "RenderedDocumentArtifact")
    rows = [
        {
            "document_id": "doc-legacy-1",
            "revision": 0,
            "document_type": "waybill",
            "payload_hash": "a" * 64,
            "template_name": "waybill_v1",
            "template_version": "1.0",
            "renderer_version": "waybill-pdf-v2",
            "status": "ready",
            "pdf_file": "documents/pdf/legacy-1.pdf",
            "pdf_sha256": "s1" + "b" * 62,
            "size_bytes": 2048,
            "rendered_at": "2026-01-10T10:00:00+00:00",
            "last_error": "",
        },
        {
            "document_id": "doc-legacy-1",
            "revision": 1,
            "document_type": "waybill",
            "payload_hash": "c" * 64,
            "template_name": "waybill_v1",
            "template_version": "1.1",
            "renderer_version": "waybill-pdf-v3",
            "status": "ready",
            "pdf_file": "documents/pdf/legacy-1-r1.pdf",
            "pdf_sha256": "s2" + "d" * 62,
            "size_bytes": 4096,
            "rendered_at": "2026-02-01T10:00:00+00:00",
            "last_error": "",
        },
        {
            "document_id": "doc-legacy-2",
            "revision": 0,
            "document_type": "waybill",
            "payload_hash": "e" * 64,
            "template_name": "waybill_v1",
            "template_version": "1.0",
            "renderer_version": "",
            "status": "failed",
            "pdf_file": "",
            "pdf_sha256": "",
            "size_bytes": 0,
            "rendered_at": None,
            "last_error": "WeasyPrint native deps missing",
        },
    ]
    created = []
    for row in rows:
        artifact = Artifact.objects.create(**row)
        created.append(row | {"id": artifact.id})
    return created


class ArtifactMigrationRoundtripTests(TransactionTestCase):
    def tearDown(self) -> None:
        # Always restore the schema to the latest migration so subsequent
        # tests run against the current model state.
        try:
            _migrate(_MIGRATION_0002)
        finally:
            super().tearDown()

    def test_forward_backward_second_forward_preserves_legacy_data(self) -> None:
        # 1. Go back to 0001 and seed production-like legacy rows.
        executor_0001 = _migrate(_MIGRATION_0001)
        apps_0001 = _app_models(executor_0001, _MIGRATION_0001)
        seeded = _create_legacy_rows(apps_0001)
        self.assertEqual(len(seeded), 3)

        # 2. Forward: 0001 -> 0002.
        executor_0002 = _migrate(_MIGRATION_0002)
        apps_0002 = _app_models(executor_0002, _MIGRATION_0002)
        ArtifactV2 = apps_0002.get_model(_APP, "RenderedDocumentArtifact")
        rows_after_forward = list(ArtifactV2.objects.order_by("id"))

        self.assertEqual(len(rows_after_forward), 3, "row count must not change")
        for original, row in zip(seeded, rows_after_forward, strict=True):
            # Document identity preserved.
            self.assertEqual(row.document_id, original["document_id"])
            self.assertEqual(row.revision, original["revision"])
            self.assertEqual(row.payload_hash, original["payload_hash"])
            # template_name correctly became template_id.
            self.assertEqual(row.template_id, original["template_name"])
            self.assertEqual(row.template_version, original["template_version"])
            # Legacy defaults filled.
            self.assertEqual(row.document_contract, LEGACY_DEFAULTS["document_contract"])
            self.assertEqual(row.engine, LEGACY_DEFAULTS["engine"])
            self.assertEqual(row.backend, LEGACY_DEFAULTS["backend"])
            self.assertEqual(row.backend_version, LEGACY_DEFAULTS["backend_version"])
            self.assertEqual(row.layout_version, LEGACY_DEFAULTS["layout_version"])
            self.assertEqual(row.render_role, LEGACY_DEFAULTS["render_role"])
            # renderer_version-specific engine_version preserved; fallback only
            # when renderer_version was empty.
            expected_engine_version = (
                original["renderer_version"] or LEGACY_DEFAULTS["engine_version_fallback"]
            )
            self.assertEqual(row.engine_version, expected_engine_version)
            # Files/hash/status/error preserved.
            self.assertEqual(row.pdf_file.name, original["pdf_file"]) if original["pdf_file"] else None
            self.assertEqual(row.pdf_sha256, original["pdf_sha256"])
            self.assertEqual(row.size_bytes, original["size_bytes"])
            self.assertEqual(row.status, original["status"])
            self.assertEqual(row.last_error, original["last_error"])
            # renderer_version kept as forensic alias.
            self.assertEqual(row.renderer_version, original["renderer_version"])

        # 3. Backward: 0002 -> 0001.
        executor_0001_back = _migrate(_MIGRATION_0001)
        apps_0001_back = _app_models(executor_0001_back, _MIGRATION_0001)
        ArtifactV1 = apps_0001_back.get_model(_APP, "RenderedDocumentArtifact")
        rows_after_backward = list(ArtifactV1.objects.order_by("id"))

        self.assertEqual(len(rows_after_backward), 3)
        for original, row in zip(seeded, rows_after_backward, strict=True):
            # template_id returned to template_name; legacy-compatible values intact.
            self.assertEqual(row.template_name, original["template_name"])
            self.assertEqual(row.template_version, original["template_version"])
            # renderer_version restored/kept for the old model.
            self.assertEqual(row.renderer_version, original["renderer_version"])
            # PDF file reference and hash not lost.
            self.assertEqual(row.pdf_file.name, original["pdf_file"]) if original["pdf_file"] else None
            self.assertEqual(row.pdf_sha256, original["pdf_sha256"])
            # document identity unchanged.
            self.assertEqual(row.document_id, original["document_id"])
            self.assertEqual(row.revision, original["revision"])
            self.assertEqual(row.payload_hash, original["payload_hash"])
            self.assertEqual(row.status, original["status"])
            self.assertEqual(row.last_error, original["last_error"])

        # 4. Second forward: 0001 -> 0002 (repeatability).
        executor_0002_again = _migrate(_MIGRATION_0002)
        apps_0002_again = _app_models(executor_0002_again, _MIGRATION_0002)
        ArtifactV2Again = apps_0002_again.get_model(_APP, "RenderedDocumentArtifact")
        rows_again = list(ArtifactV2Again.objects.order_by("id"))
        self.assertEqual(len(rows_again), 3)
        for original, row in zip(seeded, rows_again, strict=True):
            self.assertEqual(row.template_id, original["template_name"])
            self.assertEqual(row.document_id, original["document_id"])
            self.assertEqual(row.revision, original["revision"])
            self.assertEqual(row.payload_hash, original["payload_hash"])
            self.assertEqual(row.pdf_sha256, original["pdf_sha256"])
            self.assertEqual(row.status, original["status"])
            expected_engine_version = (
                original["renderer_version"] or LEGACY_DEFAULTS["engine_version_fallback"]
            )
            self.assertEqual(row.engine_version, expected_engine_version)
            self.assertEqual(row.render_role, LEGACY_DEFAULTS["render_role"])

    def test_v2_identity_axes_are_not_null_after_forward(self) -> None:
        _migrate(_MIGRATION_0001)
        executor_0001 = _executor()
        apps_0001 = _app_models(executor_0001, _MIGRATION_0001)
        _create_legacy_rows(apps_0001)

        executor_0002 = _migrate(_MIGRATION_0002)
        apps_0002 = _app_models(executor_0002, _MIGRATION_0002)
        ArtifactV2 = apps_0002.get_model(_APP, "RenderedDocumentArtifact")

        for row in ArtifactV2.objects.all():
            for field in (
                "document_contract",
                "template_id",
                "engine",
                "engine_version",
                "backend",
                "backend_version",
                "render_role",
                "layout_version",
            ):
                value = getattr(row, field)
                self.assertIsNotNone(value, f"v2 axis {field!r} must be NOT NULL")
                self.assertNotEqual(value, "", f"v2 axis {field!r} must be backfilled")
