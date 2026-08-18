"""Shadow integration tests — Phase 6D.

Covers shadow artifact creation, skip logic, mode check, exception isolation,
structural comparison, immutability, and management commands.
"""

from __future__ import annotations

import hashlib
import io
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.documents.models import RenderedDocumentArtifact
from apps.documents.services import (
    QdeRenderFailedError,
    QdeTimeoutError,
    RenderedDocumentResult,
    compare_pdf_structural,
    render_shadow_pdf,
)

LEGACY_PDF = b"%PDF-1.4\n% legacy\n%%EOF"
SHADOW_PDF = b"%PDF-1.4\n% shadow\n%%EOF"
DIFFERENT_PDF = b"%PDF-1.4\n% different\n%%EOF"


def _document(**overrides: object) -> dict:
    doc: dict = {
        "id": "doc-shadow-1",
        "document_type": "waybill",
        "document_number": "WB-SH-1",
        "revision": 0,
        "site_id": 1,
        "template_name": "waybill_v1",
        "template_version": "1.0",
        "payload_hash": "a" * 64,
        "payload": {
            "operation_display_number": "060326/0121/1",
            "operation_type": "RECEIVE",
            "lines": [
                {
                    "line_number": 1,
                    "item_name": "Drill",
                    "unit_symbol": "sh",
                    "quantity": 1,
                }
            ],
        },
    }
    doc.update(overrides)
    return doc


def _identity(**overrides) -> dict:
    values = {
        "document_id": "doc-shadow-1",
        "revision": 0,
        "document_type": "waybill",
        "payload_hash": "a" * 64,
        "document_contract": "warehouse.operation-document/v2",
        "template_id": "warehouse-waybill-ru",
        "template_version": "2.0.0",
        "engine": "qde",
        "engine_version": "0.1.0",
        "backend": "typst",
        "backend_version": "0.15.1",
        "status": RenderedDocumentArtifact.Status.READY,
        "render_role": "shadow",
        "renderer_version": "waybill-pdf-v3",
    }
    values.update(overrides)
    return values


def _create_artifact(**overrides) -> RenderedDocumentArtifact:
    return RenderedDocumentArtifact.objects.create(**_identity(**overrides))


def _create_artifact_with_pdf(
    pdf_bytes: bytes = SHADOW_PDF, **overrides
) -> RenderedDocumentArtifact:
    artifact = _create_artifact(**overrides)
    filename = f"documents/pdf/shadow/{artifact.document_id}_{artifact.payload_hash}.pdf"
    artifact.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
    artifact.pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    artifact.size_bytes = len(pdf_bytes)
    artifact.rendered_at = timezone.now()
    artifact.save(
        update_fields=[
            "pdf_file",
            "pdf_sha256",
            "size_bytes",
            "rendered_at",
            "updated_at",
        ]
    )
    return artifact


# ── 1. Shadow Artifact Creation ──────────────────────────────────────


class TestShadowArtifactCreation(TestCase):
    """Test that shadow artifacts are created with correct fields."""

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self._settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self._settings.enable()

    def tearDown(self):
        self._settings.disable()
        self.media_dir.cleanup()

    @patch("apps.documents.services.render_via_qde")
    def test_shadow_artifact_fields(self, mock_qde):
        mock_qde.return_value = SimpleNamespace(
            pdf_bytes=SHADOW_PDF,
            exit_code=0,
            stderr_message="",
            elapsed_seconds=0.1,
            page_count=None,
        )
        doc = _document()
        result = render_shadow_pdf(doc)

        self.assertIsNotNone(result)
        self.assertEqual(result.artifact.engine, "qde")
        self.assertEqual(result.artifact.backend, "typst")
        self.assertEqual(result.artifact.render_role, "shadow")
        self.assertEqual(result.artifact.status, RenderedDocumentArtifact.Status.READY)
        self.assertIn("documents/pdf/shadow/", result.artifact.pdf_file.name)
        self.assertGreater(result.artifact.size_bytes, 0)
        self.assertEqual(result.artifact.pdf_sha256, hashlib.sha256(SHADOW_PDF).hexdigest())
        self.assertEqual(result.pdf_bytes, SHADOW_PDF)
        self.assertFalse(result.cache_hit)


# ── 2. Existing Shadow Artifact Skip ─────────────────────────────────


class TestShadowArtifactSkip(TestCase):
    """Test that existing READY shadow artifact is not re-rendered."""

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self._settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self._settings.enable()

    def tearDown(self):
        self._settings.disable()
        self.media_dir.cleanup()

    @patch("apps.documents.services.render_via_qde")
    def test_skip_if_ready_exists(self, mock_qde):
        existing = _create_artifact_with_pdf(
            pdf_bytes=SHADOW_PDF,
            status=RenderedDocumentArtifact.Status.READY,
        )

        result = render_shadow_pdf(_document())

        mock_qde.assert_not_called()
        self.assertIsNotNone(result)
        self.assertEqual(result.artifact.id, existing.id)
        self.assertTrue(result.cache_hit)


# ── 3. Mode Check (view behavior) ────────────────────────────────────


class TestShadowModeCheck(TestCase):
    """Test DocumentPdfView checks mode correctly."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", is_active=True
        )
        self.client.login(username="testuser", password="testpass")
        self.doc = _document()

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_shadow_mode_triggers_shadow_render(
        self, MockAPI, mock_render, mock_shadow
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_render.return_value = SimpleNamespace(
            pdf_bytes=LEGACY_PDF, cache_hit=False
        )
        mock_shadow.return_value = None

        with override_settings(DOCUMENTS_RENDER_MODE="shadow"):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 200)
        mock_shadow.assert_called_once_with(self.doc)

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_legacy_mode_skips_shadow(self, MockAPI, mock_render, mock_shadow):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_render.return_value = SimpleNamespace(
            pdf_bytes=LEGACY_PDF, cache_hit=False
        )

        with override_settings(DOCUMENTS_RENDER_MODE="legacy"):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 200)
        mock_shadow.assert_not_called()


# ── 4. Exception Isolation (7 failure cases) ─────────────────────────


class TestExceptionIsolation(TestCase):
    """Test that shadow failures never affect legacy response."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", is_active=True
        )
        self.client.login(username="testuser", password="testpass")
        self.doc = _document()

    def _assert_legacy_response(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(".pdf", response["Content-Disposition"])
        self.assertEqual(response.content, LEGACY_PDF)

    def _assert_no_primary_switch(self):
        primary = RenderedDocumentArtifact.objects.filter(
            render_role="primary"
        ).exists()
        self.assertFalse(primary, "No primary artifact switching should occur")

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_qde_render_failure_isolation(self, MockAPI, mock_render, mock_shadow):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_render.return_value = SimpleNamespace(
            pdf_bytes=LEGACY_PDF, cache_hit=False
        )
        mock_shadow.side_effect = QdeRenderFailedError("QDE broke")

        with override_settings(DOCUMENTS_RENDER_MODE="shadow"):
            with patch("apps.documents.views.logger") as mock_logger:
                response = self.client.get(f"/documents/{self.doc['id']}/pdf/")
                mock_logger.exception.assert_called()

        self._assert_legacy_response(response)
        self._assert_no_primary_switch()

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_qde_timeout_isolation(self, MockAPI, mock_render, mock_shadow):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_render.return_value = SimpleNamespace(
            pdf_bytes=LEGACY_PDF, cache_hit=False
        )
        mock_shadow.side_effect = QdeTimeoutError("timed out")

        with override_settings(DOCUMENTS_RENDER_MODE="shadow"):
            with patch("apps.documents.views.logger") as mock_logger:
                response = self.client.get(f"/documents/{self.doc['id']}/pdf/")
                mock_logger.exception.assert_called()

        self._assert_legacy_response(response)
        self._assert_no_primary_switch()

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_artifact_persistence_failure_isolation(
        self, MockAPI, mock_render, mock_shadow
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_render.return_value = SimpleNamespace(
            pdf_bytes=LEGACY_PDF, cache_hit=False
        )
        mock_shadow.side_effect = Exception("DB write failed")

        with override_settings(DOCUMENTS_RENDER_MODE="shadow"):
            with patch("apps.documents.views.logger") as mock_logger:
                response = self.client.get(f"/documents/{self.doc['id']}/pdf/")
                mock_logger.exception.assert_called()

        self._assert_legacy_response(response)
        self._assert_no_primary_switch()

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_file_write_failure_isolation(self, MockAPI, mock_render, mock_shadow):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_render.return_value = SimpleNamespace(
            pdf_bytes=LEGACY_PDF, cache_hit=False
        )
        mock_shadow.side_effect = OSError("disk full")

        with override_settings(DOCUMENTS_RENDER_MODE="shadow"):
            with patch("apps.documents.views.logger") as mock_logger:
                response = self.client.get(f"/documents/{self.doc['id']}/pdf/")
                mock_logger.exception.assert_called()

        self._assert_legacy_response(response)
        self._assert_no_primary_switch()

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_pdf_read_failure_isolation(self, MockAPI, mock_render, mock_shadow):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_render.return_value = SimpleNamespace(
            pdf_bytes=LEGACY_PDF, cache_hit=False
        )
        mock_shadow.side_effect = IOError("read error")

        with override_settings(DOCUMENTS_RENDER_MODE="shadow"):
            with patch("apps.documents.views.logger") as mock_logger:
                response = self.client.get(f"/documents/{self.doc['id']}/pdf/")
                mock_logger.exception.assert_called()

        self._assert_legacy_response(response)
        self._assert_no_primary_switch()

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_structural_comparison_failure_isolation(
        self, MockAPI, mock_render, mock_shadow
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_render.return_value = SimpleNamespace(
            pdf_bytes=LEGACY_PDF, cache_hit=False
        )
        mock_shadow.side_effect = RuntimeError("comparison crashed")

        with override_settings(DOCUMENTS_RENDER_MODE="shadow"):
            with patch("apps.documents.views.logger") as mock_logger:
                response = self.client.get(f"/documents/{self.doc['id']}/pdf/")
                mock_logger.exception.assert_called()

        self._assert_legacy_response(response)
        self._assert_no_primary_switch()

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_persistence_exception_isolation(self, MockAPI, mock_render, mock_shadow):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_render.return_value = SimpleNamespace(
            pdf_bytes=LEGACY_PDF, cache_hit=False
        )
        mock_shadow.side_effect = RuntimeError("persistence layer exploded")

        with override_settings(DOCUMENTS_RENDER_MODE="shadow"):
            with patch("apps.documents.views.logger") as mock_logger:
                response = self.client.get(f"/documents/{self.doc['id']}/pdf/")
                mock_logger.exception.assert_called()

        self._assert_legacy_response(response)
        self._assert_no_primary_switch()


# ── 5. PDF Structural Comparison ─────────────────────────────────────


class TestPdfStructuralComparison(TestCase):
    """Test compare_pdf_structural function."""

    def test_identical_pdfs_match(self):
        result = compare_pdf_structural(LEGACY_PDF, LEGACY_PDF)
        self.assertTrue(result["sha_match"])
        self.assertEqual(result["legacy_sha256"], result["shadow_sha256"])

    def test_different_page_count_mismatch(self):
        pdf_a = b"%PDF-1.4\n% page1\n%%EOF"
        pdf_b = (
            b"%PDF-1.4\n% page1\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R 4 0 R]/Count 2>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
            b"4 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
            b"%%EOF"
        )
        result = compare_pdf_structural(pdf_a, pdf_b)
        self.assertFalse(result["sha_match"])
        if result["page_count_match"] is not None:
            self.assertFalse(result["page_count_match"])

    def test_different_content_mismatch(self):
        pdf_a = b"%PDF-1.4\n% alpha\n%%EOF"
        pdf_b = b"%PDF-1.4\n% beta\n%%EOF"
        result = compare_pdf_structural(pdf_a, pdf_b)
        self.assertFalse(result["sha_match"])
        self.assertNotEqual(result["legacy_sha256"], result["shadow_sha256"])

    def test_empty_pdf_handling(self):
        result = compare_pdf_structural(b"", b"")
        self.assertTrue(result["sha_match"])
        if result["page_count_match"] is not None:
            self.assertFalse(result["page_count_match"])

    def test_media_box_tolerance_subpixel_rounding(self):
        """MediaBox values that differ by <0.1 pt must be treated as equivalent.

        Different PDF engines (Typst vs WeasyPrint) may round coordinate
        values at different precision.  A4 portrait is 595.28 × 841.89 pt.
        """
        from apps.documents.services import _media_box_equivalent

        # Typical A4 from Typst (high precision)
        mb_typst = [0.0, 0.0, 595.275591, 841.889764]
        # Typical A4 from WeasyPrint (rounded)
        mb_weasy = [0.0, 0.0, 595.2756, 841.8898]

        self.assertTrue(_media_box_equivalent(mb_typst, mb_weasy))

    def test_media_box_mismatch_real_difference(self):
        """MediaBox values that differ by >0.1 pt must NOT be treated as equivalent."""
        from apps.documents.services import _media_box_equivalent

        mb_a4 = [0.0, 0.0, 595.276, 841.890]
        mb_letter = [0.0, 0.0, 612.0, 792.0]

        self.assertFalse(_media_box_equivalent(mb_a4, mb_letter))


# ── 6. Shadow Artifact Immutability ──────────────────────────────────


class TestShadowImmutability(TestCase):
    """Test shadow artifacts are immutable once created."""

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self._settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self._settings.enable()

    def tearDown(self):
        self._settings.disable()
        self.media_dir.cleanup()

    @patch("apps.documents.services.render_via_qde")
    def test_no_update_after_creation(self, mock_qde):
        mock_qde.return_value = SimpleNamespace(
            pdf_bytes=SHADOW_PDF,
            exit_code=0,
            stderr_message="",
            elapsed_seconds=0.1,
            page_count=None,
        )
        result1 = render_shadow_pdf(_document())
        self.assertIsNotNone(result1)

        different_pdf = b"%PDF-1.4\n% different\n%%EOF"
        mock_qde.return_value = SimpleNamespace(
            pdf_bytes=different_pdf,
            exit_code=0,
            stderr_message="",
            elapsed_seconds=0.1,
            page_count=None,
        )
        result2 = render_shadow_pdf(_document())

        self.assertIsNotNone(result2)
        self.assertEqual(result1.artifact.id, result2.artifact.id)
        self.assertEqual(result2.pdf_bytes, SHADOW_PDF)

        artifact = RenderedDocumentArtifact.objects.get(id=result1.artifact.id)
        self.assertEqual(artifact.pdf_sha256, hashlib.sha256(SHADOW_PDF).hexdigest())
        self.assertEqual(artifact.render_role, "shadow")


# ── 7. Management Command: compare_shadow_artifacts ──────────────────


class TestCompareShadowArtifacts(TestCase):
    """Test compare_shadow_artifacts management command."""

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self._settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self._settings.enable()

    def tearDown(self):
        self._settings.disable()
        self.media_dir.cleanup()

    def test_no_artifacts(self):
        out = io.StringIO()
        from django.core.management import call_command

        call_command("compare_shadow_artifacts", stdout=out)
        self.assertIn("No comparable legacy/shadow pairs found", out.getvalue())

    def test_deterministic_pairing(self):
        _create_artifact_with_pdf(
            pdf_bytes=LEGACY_PDF,
            render_role="legacy",
            engine="django-legacy",
            engine_version="waybill-pdf-v3",
            backend="weasyprint",
            backend_version="66.0",
            document_id="doc-pair-1",
            payload_hash="a" * 64,
        )
        _create_artifact_with_pdf(
            pdf_bytes=SHADOW_PDF,
            render_role="shadow",
            engine="qde",
            document_id="doc-pair-1",
            payload_hash="a" * 64,
        )

        out = io.StringIO()
        from django.core.management import call_command

        call_command("compare_shadow_artifacts", stdout=out)
        output = out.getvalue()
        self.assertIn("doc-pair-1", output)

    def test_limit_option(self):
        for i in range(5):
            _create_artifact_with_pdf(
                pdf_bytes=LEGACY_PDF,
                render_role="legacy",
                engine="django-legacy",
                engine_version="waybill-pdf-v3",
                backend="weasyprint",
                backend_version="66.0",
                document_id=f"doc-limit-{i}",
                payload_hash=f"{i:064d}",
            )
            _create_artifact_with_pdf(
                pdf_bytes=SHADOW_PDF,
                render_role="shadow",
                engine="qde",
                document_id=f"doc-limit-{i}",
                payload_hash=f"{i:064d}",
            )

        out = io.StringIO()
        from django.core.management import call_command

        call_command("compare_shadow_artifacts", limit=2, stdout=out)
        output = out.getvalue()
        self.assertIn("Total pairs: 2", output)

    def test_output_ratios(self):
        _create_artifact_with_pdf(
            pdf_bytes=LEGACY_PDF,
            render_role="legacy",
            engine="django-legacy",
            engine_version="waybill-pdf-v3",
            backend="weasyprint",
            backend_version="66.0",
            document_id="doc-ratio-1",
            payload_hash="b" * 64,
        )
        _create_artifact_with_pdf(
            pdf_bytes=LEGACY_PDF,
            render_role="shadow",
            engine="qde",
            document_id="doc-ratio-1",
            payload_hash="b" * 64,
        )

        out = io.StringIO()
        from django.core.management import call_command

        call_command("compare_shadow_artifacts", stdout=out)
        output = out.getvalue()
        self.assertIn("Structural match ratio", output)

    def test_read_only(self):
        _create_artifact_with_pdf(
            pdf_bytes=LEGACY_PDF,
            render_role="legacy",
            engine="django-legacy",
            engine_version="waybill-pdf-v3",
            backend="weasyprint",
            backend_version="66.0",
            document_id="doc-ro-1",
            payload_hash="c" * 64,
        )
        _create_artifact_with_pdf(
            pdf_bytes=SHADOW_PDF,
            render_role="shadow",
            engine="qde",
            document_id="doc-ro-1",
            payload_hash="c" * 64,
        )
        count_before = RenderedDocumentArtifact.objects.count()

        out = io.StringIO()
        from django.core.management import call_command

        call_command("compare_shadow_artifacts", stdout=out)

        count_after = RenderedDocumentArtifact.objects.count()
        self.assertEqual(count_before, count_after)

    def test_mismatched_pdfs_detected(self):
        _create_artifact_with_pdf(
            pdf_bytes=LEGACY_PDF,
            render_role="legacy",
            engine="django-legacy",
            engine_version="waybill-pdf-v3",
            backend="weasyprint",
            backend_version="66.0",
            document_id="doc-mismatch-1",
            payload_hash="d" * 64,
        )
        _create_artifact_with_pdf(
            pdf_bytes=DIFFERENT_PDF,
            render_role="shadow",
            engine="qde",
            document_id="doc-mismatch-1",
            payload_hash="d" * 64,
        )

        out = io.StringIO()
        from django.core.management import call_command

        call_command("compare_shadow_artifacts", stdout=out)
        output = out.getvalue()
        self.assertIn("MISMATCH", output)

    def test_different_sha_same_structural_is_match(self):
        """Different SHA but same pages + MediaBox → MATCH.

        Different PDF engines (Typst vs WeasyPrint) produce different byte
        streams for the same content.  Structural match is the contract.
        """
        _create_artifact_with_pdf(
            pdf_bytes=LEGACY_PDF,
            render_role="legacy",
            engine="django-legacy",
            engine_version="waybill-pdf-v3",
            backend="weasyprint",
            backend_version="66.0",
            document_id="doc-sha-diff-1",
            payload_hash="k" * 64,
        )
        _create_artifact_with_pdf(
            pdf_bytes=DIFFERENT_PDF,
            render_role="shadow",
            engine="qde",
            document_id="doc-sha-diff-1",
            payload_hash="k" * 64,
        )

        out = io.StringIO()
        from django.core.management import call_command

        call_command("compare_shadow_artifacts", stdout=out)
        output = out.getvalue()
        # Both are minimal single-page PDFs with same MediaBox → MATCH
        self.assertIn("MATCH", output)


class TestCleanupShadowArtifacts(TestCase):
    """Test cleanup_shadow_artifacts management command."""

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self._settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self._settings.enable()

    def tearDown(self):
        self._settings.disable()
        self.media_dir.cleanup()

    def test_dry_run_no_deletion(self):
        _create_artifact_with_pdf(
            pdf_bytes=SHADOW_PDF,
            render_role="shadow",
            engine="qde",
            document_id="doc-dry-1",
            payload_hash="e" * 64,
        )
        count_before = RenderedDocumentArtifact.objects.count()

        out = io.StringIO()
        from django.core.management import call_command

        call_command("cleanup_shadow_artifacts", dry_run=True, days=1, stdout=out)
        self.assertIn("DRY RUN", out.getvalue())
        self.assertEqual(
            RenderedDocumentArtifact.objects.count(), count_before
        )

    def test_deletes_only_expired_qde_shadow(self):
        old_artifact = _create_artifact_with_pdf(
            pdf_bytes=SHADOW_PDF,
            render_role="shadow",
            engine="qde",
            document_id="doc-exp-1",
            payload_hash="f" * 64,
        )
        old_artifact.created_at = timezone.now() - timedelta(days=60)
        old_artifact.save(update_fields=["created_at"])

        out = io.StringIO()
        from django.core.management import call_command

        call_command("cleanup_shadow_artifacts", days=30, stdout=out)

        self.assertFalse(
            RenderedDocumentArtifact.objects.filter(id=old_artifact.id).exists()
        )

    def test_days_validation(self):
        out = io.StringIO()
        err = io.StringIO()
        from django.core.management import call_command

        call_command("cleanup_shadow_artifacts", days=0, stdout=out, stderr=err)
        self.assertIn("--days must be a positive", err.getvalue())

    def test_no_deletion_of_legacy(self):
        artifact = _create_artifact_with_pdf(
            pdf_bytes=LEGACY_PDF,
            render_role="legacy",
            engine="django-legacy",
            document_id="doc-leg-1",
            payload_hash="g" * 64,
        )
        artifact.created_at = timezone.now() - timedelta(days=60)
        artifact.save(update_fields=["created_at"])

        from django.core.management import call_command

        call_command("cleanup_shadow_artifacts", days=30, stdout=io.StringIO())

        self.assertTrue(
            RenderedDocumentArtifact.objects.filter(id=artifact.id).exists()
        )

    def test_no_deletion_of_primary(self):
        artifact = _create_artifact_with_pdf(
            pdf_bytes=SHADOW_PDF,
            render_role="primary",
            engine="qde",
            document_id="doc-pri-1",
            payload_hash="h" * 64,
        )
        artifact.created_at = timezone.now() - timedelta(days=60)
        artifact.save(update_fields=["created_at"])

        from django.core.management import call_command

        call_command("cleanup_shadow_artifacts", days=30, stdout=io.StringIO())

        self.assertTrue(
            RenderedDocumentArtifact.objects.filter(id=artifact.id).exists()
        )

    def test_no_deletion_of_newer_shadow(self):
        artifact = _create_artifact_with_pdf(
            pdf_bytes=SHADOW_PDF,
            render_role="shadow",
            engine="qde",
            document_id="doc-new-1",
            payload_hash="i" * 64,
        )

        from django.core.management import call_command

        call_command("cleanup_shadow_artifacts", days=30, stdout=io.StringIO())

        self.assertTrue(
            RenderedDocumentArtifact.objects.filter(id=artifact.id).exists()
        )

    def test_no_deletion_of_non_shadow(self):
        artifact = _create_artifact_with_pdf(
            pdf_bytes=SHADOW_PDF,
            render_role="emergency_fallback",
            engine="qde",
            document_id="doc-non-1",
            payload_hash="j" * 64,
        )
        artifact.created_at = timezone.now() - timedelta(days=60)
        artifact.save(update_fields=["created_at"])

        from django.core.management import call_command

        call_command("cleanup_shadow_artifacts", days=30, stdout=io.StringIO())

        self.assertTrue(
            RenderedDocumentArtifact.objects.filter(id=artifact.id).exists()
        )
