"""QDE primary cutover tests — Phase 6F.

Covers the primary artifact lifecycle (persist/reuse/stale revision),
QDE-mode view routing, no-silent-fallback semantics, the operator-enabled
emergency fallback (explicit label + artifact role) and the legacy/shadow
regression paths. See TZ-QDE_INTEGRATION_READINESS §6.4/§10.6.
"""

from __future__ import annotations

import hashlib
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.documents.models import RenderedDocumentArtifact
from apps.documents.services import (
    DEFAULT_LEGACY_AXES,
    QDE_ARTIFACT_IDENTITY_FIELDS,
    QdeBackendUnavailableError,
    QdeRenderFailedError,
    QdeTimeoutError,
    _qde_shadow_identity,
    render_document_pdf,
    render_qde_primary,
)

QDE_PDF = b"%PDF-1.4\n% qde primary\n%%EOF"
LEGACY_PDF = b"%PDF-1.4\n% legacy\n%%EOF"
STALE_PDF = b"%PDF-1.4\n% stale\n%%EOF"

MAPPED_TEMPLATE_ID = settings.DOCUMENT_TEMPLATE_MAP["waybill"][0]
MAPPED_TEMPLATE_VERSION = settings.DOCUMENT_TEMPLATE_MAP["waybill"][1]


def _document(**overrides: object) -> dict:
    doc: dict = {
        "id": "doc-primary-1",
        "document_type": "waybill",
        "document_number": "WB-PR-1",
        "revision": 0,
        "site_id": 1,
        "template_name": "waybill_v1",
        "template_version": "1.0",
        "payload_hash": "a" * 64,
        "payload": {
            "operation_display_number": "060326/0121/1",
            "operation_type": "RECEIVE",
            "consignee_label": "Base",
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


def _qde_result(pdf_bytes: bytes = QDE_PDF) -> SimpleNamespace:
    return SimpleNamespace(
        pdf_bytes=pdf_bytes,
        exit_code=0,
        stderr_message="",
        elapsed_seconds=0.05,
        page_count=None,
    )


def _current_identity(**overrides) -> dict:
    """Full QDE render identity resolved exactly like render_qde_primary does."""
    identity = _qde_shadow_identity(_document())
    identity.update(overrides)
    return identity


def _create_artifact_with_pdf(
    pdf_bytes: bytes,
    *,
    render_role: str = "primary",
    filename: str | None = None,
    **axis_overrides,
) -> RenderedDocumentArtifact:
    identity = _current_identity()
    fields = {field: identity[field] for field in QDE_ARTIFACT_IDENTITY_FIELDS}
    fields["document_type"] = identity["document_type"]
    fields["renderer_version"] = identity["renderer_version"]
    fields["render_role"] = render_role
    fields["status"] = RenderedDocumentArtifact.Status.READY
    fields.update(axis_overrides)

    artifact = RenderedDocumentArtifact.objects.create(**fields)
    if filename is None:
        filename = f"documents/pdf/{artifact.document_id}_{artifact.payload_hash}.pdf"
    artifact.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
    artifact.pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    artifact.size_bytes = len(pdf_bytes)
    artifact.rendered_at = timezone.now()
    artifact.save(
        update_fields=["pdf_file", "pdf_sha256", "size_bytes", "rendered_at", "updated_at"]
    )
    return artifact


class TestQdePrimaryService(TestCase):
    """Service-level behavior of render_qde_primary (TZ §5.5/§6.4/§6.6)."""

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self._settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self._settings.enable()

    def tearDown(self):
        self._settings.disable()
        self.media_dir.cleanup()

    @patch("apps.documents.services.render_via_qde")
    def test_primary_artifact_axes_and_storage(self, mock_qde):
        mock_qde.return_value = _qde_result()

        result = render_qde_primary(_document())

        self.assertFalse(result.cache_hit)
        self.assertEqual(result.pdf_bytes, QDE_PDF)
        artifact = result.artifact
        self.assertEqual(artifact.engine, "qde")
        self.assertEqual(artifact.backend, "typst")
        self.assertEqual(artifact.backend_version, "0.15.1")
        self.assertEqual(artifact.engine_version, "1.0.0")
        self.assertEqual(artifact.document_contract, "warehouse.operation-document/v2")
        self.assertEqual(artifact.template_id, MAPPED_TEMPLATE_ID)
        self.assertEqual(artifact.template_version, MAPPED_TEMPLATE_VERSION)
        self.assertEqual(artifact.document_type, "waybill")
        self.assertEqual(artifact.render_role, "primary")
        self.assertEqual(artifact.status, RenderedDocumentArtifact.Status.READY)
        self.assertEqual(artifact.pdf_sha256, hashlib.sha256(QDE_PDF).hexdigest())
        self.assertEqual(artifact.size_bytes, len(QDE_PDF))
        self.assertTrue(artifact.pdf_file.name.startswith("documents/pdf/"))
        self.assertNotIn("shadow", artifact.pdf_file.name)
        self.assertTrue(artifact.is_ready)

    @patch("apps.documents.services.render_via_qde")
    def test_primary_reuses_ready_primary_artifact_without_rerender(self, mock_qde):
        existing = _create_artifact_with_pdf(QDE_PDF, render_role="primary")

        result = render_qde_primary(_document())

        mock_qde.assert_not_called()
        self.assertTrue(result.cache_hit)
        self.assertEqual(result.artifact.id, existing.id)
        self.assertEqual(result.pdf_bytes, QDE_PDF)

    @patch("apps.documents.services.render_via_qde")
    def test_primary_reuses_ready_shadow_artifact_as_cache_hit(self, mock_qde):
        """TZ §6.6: a shadow artifact is a valid later primary cache hit."""
        shadow = _create_artifact_with_pdf(QDE_PDF, render_role="shadow")

        result = render_qde_primary(_document())

        mock_qde.assert_not_called()
        self.assertTrue(result.cache_hit)
        self.assertEqual(result.artifact.id, shadow.id)
        shadow.refresh_from_db()
        self.assertEqual(shadow.render_role, "shadow")  # creation role immutable

    @patch("apps.documents.services.render_via_qde")
    def test_primary_does_not_reuse_stale_template_revision(self, mock_qde):
        mock_qde.return_value = _qde_result()
        _create_artifact_with_pdf(STALE_PDF, render_role="primary", template_version="1.0.0")

        result = render_qde_primary(_document())

        mock_qde.assert_called_once()
        self.assertFalse(result.cache_hit)
        self.assertEqual(result.artifact.template_version, MAPPED_TEMPLATE_VERSION)
        self.assertEqual(result.pdf_bytes, QDE_PDF)

    @patch("apps.documents.services.render_via_qde")
    def test_primary_propagates_qde_render_error(self, mock_qde):
        mock_qde.side_effect = QdeRenderFailedError("Typst panic")

        with self.assertRaises(QdeRenderFailedError):
            render_qde_primary(_document())

        self.assertFalse(
            RenderedDocumentArtifact.objects.filter(
                document_id="doc-primary-1",
                status=RenderedDocumentArtifact.Status.READY,
            ).exists()
        )

    @patch("apps.documents.services.render_via_qde")
    def test_primary_propagates_backend_unavailable(self, mock_qde):
        mock_qde.side_effect = QdeBackendUnavailableError("no typst binary")

        with self.assertRaises(QdeBackendUnavailableError):
            render_qde_primary(_document())

    @patch("apps.documents.services._render_html_to_pdf_bytes", return_value=LEGACY_PDF)
    def test_legacy_renderer_default_role_is_legacy(self, _mock_render):
        result = render_document_pdf(_document(id="doc-legacy-role"))

        self.assertEqual(result.artifact.render_role, "legacy")

    @patch("apps.documents.services._render_html_to_pdf_bytes", return_value=LEGACY_PDF)
    def test_legacy_renderer_emergency_role_is_explicit(self, _mock_render):
        result = render_document_pdf(
            _document(id="doc-emergency-role"),
            render_role="emergency_fallback",
        )

        self.assertEqual(result.artifact.render_role, "emergency_fallback")
        self.assertEqual(result.artifact.engine, DEFAULT_LEGACY_AXES["engine"])
        self.assertEqual(result.artifact.backend, DEFAULT_LEGACY_AXES["backend"])
        self.assertEqual(result.artifact.status, RenderedDocumentArtifact.Status.READY)


class TestQdeModeView(TestCase):
    """DocumentPdfView routing in DOCUMENTS_RENDER_MODE=qde."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", is_active=True
        )
        self.client.login(username="testuser", password="testpass")
        self.doc = _document()

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.render_qde_primary")
    @patch("apps.documents.views.DocumentsAPI")
    def test_qde_mode_returns_qde_pdf(
        self, MockAPI, mock_primary, mock_legacy, mock_shadow
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_primary.return_value = SimpleNamespace(pdf_bytes=QDE_PDF, cache_hit=False)

        with override_settings(DOCUMENTS_RENDER_MODE="qde"):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, QDE_PDF)
        self.assertEqual(response["X-Document-Pdf-Cache"], "miss")
        mock_primary.assert_called_once_with(self.doc)
        mock_legacy.assert_not_called()
        mock_shadow.assert_not_called()

    @patch("apps.documents.views.render_qde_primary")
    @patch("apps.documents.views.DocumentsAPI")
    def test_qde_mode_reports_cache_hit(self, MockAPI, mock_primary):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_primary.return_value = SimpleNamespace(pdf_bytes=QDE_PDF, cache_hit=True)

        with override_settings(DOCUMENTS_RENDER_MODE="qde"):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Document-Pdf-Cache"], "hit")

    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.render_qde_primary")
    @patch("apps.documents.views.DocumentsAPI")
    def test_qde_failure_without_fallback_never_serves_legacy(
        self, MockAPI, mock_primary, mock_legacy
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_primary.side_effect = QdeRenderFailedError("Typst panic")

        with (
            override_settings(
                DOCUMENTS_RENDER_MODE="qde", QDE_EMERGENCY_FALLBACK_ENABLED=False
            ),
            patch("apps.documents.views.logger") as mock_logger,
        ):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 500)  # RENDER_FAILED §7.4
        self.assertNotEqual(response.get("Content-Type"), "application/pdf")
        self.assertNotIn("X-QDE-Fallback", response)
        self.assertIn(b"RENDER_FAILED", response.content)
        mock_legacy.assert_not_called()
        mock_logger.warning.assert_called()

    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.render_qde_primary")
    @patch("apps.documents.views.DocumentsAPI")
    def test_qde_timeout_without_fallback_returns_503_retry_after(
        self, MockAPI, mock_primary, mock_legacy
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_primary.side_effect = QdeTimeoutError("timed out")

        with override_settings(
            DOCUMENTS_RENDER_MODE="qde", QDE_EMERGENCY_FALLBACK_ENABLED=False
        ):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "5")
        mock_legacy.assert_not_called()


class TestEmergencyFallback(TestCase):
    """Operator-enabled emergency fallback (TZ §6.4.1/§6.4.3)."""

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self._settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self._settings.enable()
        self.user = User.objects.create_user(
            username="testuser", password="testpass", is_active=True
        )
        self.client.login(username="testuser", password="testpass")
        self.doc = _document(id="doc-fallback-1")

    def tearDown(self):
        self._settings.disable()
        self.media_dir.cleanup()

    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.render_qde_primary")
    @patch("apps.documents.views.DocumentsAPI")
    def test_fallback_returns_legacy_pdf_with_explicit_label(
        self, MockAPI, mock_primary, mock_legacy
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_primary.side_effect = QdeRenderFailedError("Typst panic")
        mock_legacy.return_value = SimpleNamespace(pdf_bytes=LEGACY_PDF, cache_hit=False)

        with (
            override_settings(
                DOCUMENTS_RENDER_MODE="qde", QDE_EMERGENCY_FALLBACK_ENABLED=True
            ),
            patch("apps.documents.views.logger") as mock_logger,
        ):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, LEGACY_PDF)
        self.assertEqual(response["X-QDE-Fallback"], "emergency")
        mock_legacy.assert_called_once_with(self.doc, render_role="emergency_fallback")
        warning_events = [call.args[0] for call in mock_logger.warning.call_args_list]
        self.assertIn("qde_emergency_fallback", warning_events)

    @patch("apps.documents.services.render_via_qde")
    @patch("apps.documents.services._render_html_to_pdf_bytes", return_value=LEGACY_PDF)
    @patch("apps.documents.views.DocumentsAPI")
    def test_fallback_persists_emergency_fallback_artifact(
        self, MockAPI, _mock_html, mock_qde
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_qde.side_effect = QdeRenderFailedError("Typst panic")

        with override_settings(
            DOCUMENTS_RENDER_MODE="qde", QDE_EMERGENCY_FALLBACK_ENABLED=True
        ):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-QDE-Fallback"], "emergency")
        artifact = RenderedDocumentArtifact.objects.get(document_id=self.doc["id"])
        self.assertEqual(artifact.render_role, "emergency_fallback")
        self.assertEqual(artifact.engine, DEFAULT_LEGACY_AXES["engine"])
        self.assertEqual(artifact.backend, DEFAULT_LEGACY_AXES["backend"])
        self.assertEqual(artifact.status, RenderedDocumentArtifact.Status.READY)


class TestModeRegression(TestCase):
    """legacy/shadow modes keep their pre-6F behavior."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", is_active=True
        )
        self.client.login(username="testuser", password="testpass")
        self.doc = _document(id="doc-mode-regression")

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_qde_primary")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_legacy_mode_uses_legacy_renderer(
        self, MockAPI, mock_legacy, mock_primary, mock_shadow
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_legacy.return_value = SimpleNamespace(pdf_bytes=LEGACY_PDF, cache_hit=False)

        with override_settings(DOCUMENTS_RENDER_MODE="legacy"):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, LEGACY_PDF)
        mock_primary.assert_not_called()
        mock_shadow.assert_not_called()

    @patch("apps.documents.views.render_shadow_pdf")
    @patch("apps.documents.views.render_qde_primary")
    @patch("apps.documents.views.render_document_pdf")
    @patch("apps.documents.views.DocumentsAPI")
    def test_shadow_mode_keeps_legacy_primary_and_shadow_attempt(
        self, MockAPI, mock_legacy, mock_primary, mock_shadow
    ):
        MockAPI.return_value.get_document.return_value = self.doc
        mock_legacy.return_value = SimpleNamespace(pdf_bytes=LEGACY_PDF, cache_hit=False)
        mock_shadow.return_value = None

        with override_settings(DOCUMENTS_RENDER_MODE="shadow"):
            response = self.client.get(f"/documents/{self.doc['id']}/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, LEGACY_PDF)
        mock_primary.assert_not_called()
        mock_shadow.assert_called_once_with(self.doc)
