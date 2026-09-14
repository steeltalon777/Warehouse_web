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

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.documents.management.commands.compare_shadow_artifacts import (
    INPUT_IDENTITY_FIELDS,
    PRODUCER_IDENTITY_FIELDS,
    _expected_shadow_axes,
)
from apps.documents.models import RenderedDocumentArtifact
from apps.documents.services import (
    DEFAULT_LEGACY_AXES,
    QDE_ARTIFACT_IDENTITY_FIELDS,
    QdeRenderFailedError,
    QdeTimeoutError,
    RenderedDocumentResult,
    _qde_shadow_identity,
    compare_pdf_structural,
    render_shadow_pdf,
)

LEGACY_PDF = b"%PDF-1.4\n% legacy\n%%EOF"
SHADOW_PDF = b"%PDF-1.4\n% shadow\n%%EOF"
DIFFERENT_PDF = b"%PDF-1.4\n% different\n%%EOF"


def _minimal_pdf_bytes(*, pages: int = 1, marker: str = "") -> bytes:
    """Build a valid minimal A4 PDF without external dependencies.

    The fake `%PDF` stubs above cannot be parsed by pypdf, so real
    MATCH/MISMATCH verdicts (page count + MediaBox) must be exercised with
    parseable pages.
    """
    page_ids: list[int] = []
    content_ids: list[int] = []
    next_id = 3
    for _ in range(pages):
        page_ids.append(next_id)
        next_id += 1
    for _ in range(pages):
        content_ids.append(next_id)
        next_id += 1

    chunks: list[bytes] = [b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"]
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    chunks.append(
        f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {pages} >>\nendobj\n".encode()
    )
    for index, page_id in enumerate(page_ids):
        chunks.append(
            f"{page_id} 0 obj\n<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 595.2756 841.8898] /Contents {content_ids[index]} 0 R >>\n"
            f"endobj\n".encode()
        )
    stream = b"BT ET\n"
    for content_id in content_ids:
        chunks.append(
            f"{content_id} 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode()
            + stream
            + b"endstream\nendobj\n"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + marker.encode() + b"\n")
    offsets: list[int] = []
    for chunk in chunks:
        offsets.append(len(out))
        out += chunk
    xref_offset = len(out)
    out += f"xref\n0 {len(chunks) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(chunks) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(out)


# Valid single-page A4 PDFs: same structure, different bytes (sha diagnostic).
PDF_ONE_PAGE = _minimal_pdf_bytes(marker="legacy")
PDF_ONE_PAGE_ALT = _minimal_pdf_bytes(marker="shadow")
PDF_TWO_PAGES = _minimal_pdf_bytes(pages=2, marker="legacy")


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
    pdf_bytes: bytes = SHADOW_PDF,
    filename: str | None = None,
    **overrides,
) -> RenderedDocumentArtifact:
    artifact = _create_artifact(**overrides)
    if filename is None:
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


def _create_shadow_with_axes(
    pdf_bytes: bytes = SHADOW_PDF,
    *,
    document_id: str = "doc-shadow-1",
    payload_hash: str = "a" * 64,
    revision: int = 0,
    filename: str | None = None,
    **axis_overrides,
) -> RenderedDocumentArtifact:
    """Create a READY shadow artifact from the CURRENT QDE axes, then mutate.

    All identity axes are resolved exactly like render_shadow_pdf does; axis
    overrides simulate historical revisions (e.g.
    ``template_version="2.2.0"``).
    """
    identity = _qde_shadow_identity(
        _document(id=document_id, payload_hash=payload_hash, revision=revision)
    )
    fields = {field: identity[field] for field in QDE_ARTIFACT_IDENTITY_FIELDS}
    fields["document_type"] = identity["document_type"]
    fields.update(axis_overrides)
    return _create_artifact_with_pdf(pdf_bytes=pdf_bytes, filename=filename, **fields)


def _create_ready_shadow_for_current_identity(
    pdf_bytes: bytes = SHADOW_PDF,
) -> RenderedDocumentArtifact:
    """Create a READY shadow artifact using the CURRENT production render identity.

    All identity axes are resolved exactly like render_shadow_pdf does, so the
    artifact is a cache hit for the same document/settings and a miss when any
    axis changes.
    """
    return _create_shadow_with_axes(pdf_bytes=pdf_bytes)


def _create_legacy_with_axes(
    pdf_bytes: bytes = LEGACY_PDF,
    *,
    document_id: str = "doc-legacy-1",
    payload_hash: str = "a" * 64,
    revision: int = 0,
    filename: str | None = None,
    **axis_overrides,
) -> RenderedDocumentArtifact:
    """Create a READY legacy artifact from the CURRENT legacy axes, then mutate.

    Mirrors render_document_pdf: engine/backend/contract come from
    DEFAULT_LEGACY_AXES, engine_version from DOCUMENT_RENDERER_VERSION.
    """
    fields = {
        "document_type": "waybill",
        "document_contract": DEFAULT_LEGACY_AXES["document_contract"],
        "template_id": "waybill_v1",
        "template_version": "1.0",
        "engine": DEFAULT_LEGACY_AXES["engine"],
        "engine_version": getattr(
            settings,
            "DOCUMENT_RENDERER_VERSION",
            DEFAULT_LEGACY_AXES["engine_version"],
        ),
        "backend": DEFAULT_LEGACY_AXES["backend"],
        "backend_version": DEFAULT_LEGACY_AXES["backend_version"],
        "render_role": "legacy",
    }
    fields.update(axis_overrides)
    return _create_artifact_with_pdf(
        pdf_bytes=pdf_bytes,
        filename=filename,
        document_id=document_id,
        payload_hash=payload_hash,
        revision=revision,
        **fields,
    )


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
        existing = _create_ready_shadow_for_current_identity()

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
    """Identity-exact pairing for compare_shadow_artifacts (Phase 6E preflight).

    A valid pair shares the full input identity (document_id, revision,
    payload_hash, document_contract) and each side must be the CURRENT
    revision of its producer: legacy rows by DEFAULT_LEGACY_AXES +
    DOCUMENT_RENDERER_VERSION, shadow rows by DOCUMENT_TEMPLATE_MAP + the
    fixed QDE axes.  Historical template/engine revisions are skipped, never
    mixed (TZ-QDE_INTEGRATION_READINESS §5.3/§5.5).
    """

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self._settings = override_settings(
            MEDIA_ROOT=self.media_dir.name,
            DOCUMENT_TEMPLATE_MAP={"waybill": ("warehouse-waybill-ru", "2.2.1")},
        )
        self._settings.enable()

    def tearDown(self):
        self._settings.disable()
        self.media_dir.cleanup()

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _run(**options) -> str:
        from django.core.management import call_command

        out = io.StringIO()
        call_command("compare_shadow_artifacts", stdout=out, **options)
        return out.getvalue()

    @staticmethod
    def _create_pair(
        *,
        document_id: str = "doc-pair-1",
        payload_hash: str = "a" * 64,
        legacy_pdf: bytes = PDF_ONE_PAGE,
        shadow_pdf: bytes = PDF_ONE_PAGE_ALT,
        legacy_axes: dict | None = None,
        shadow_axes: dict | None = None,
    ) -> None:
        _create_legacy_with_axes(
            pdf_bytes=legacy_pdf,
            document_id=document_id,
            payload_hash=payload_hash,
            **(legacy_axes or {}),
        )
        _create_shadow_with_axes(
            pdf_bytes=shadow_pdf,
            document_id=document_id,
            payload_hash=payload_hash,
            **(shadow_axes or {}),
        )

    # -- identity axes ---------------------------------------------------

    def test_pairing_axes_cover_canonical_render_identity(self):
        """The pairing split must cover exactly QDE_ARTIFACT_IDENTITY_FIELDS."""
        self.assertEqual(
            set(INPUT_IDENTITY_FIELDS) | set(PRODUCER_IDENTITY_FIELDS),
            set(QDE_ARTIFACT_IDENTITY_FIELDS),
        )
        self.assertFalse(set(INPUT_IDENTITY_FIELDS) & set(PRODUCER_IDENTITY_FIELDS))
        self.assertEqual(
            list(QDE_ARTIFACT_IDENTITY_FIELDS)[: len(INPUT_IDENTITY_FIELDS)],
            list(INPUT_IDENTITY_FIELDS),
        )

    def test_expected_shadow_axes_mirror_render_identity(self):
        """Expected shadow axes must equal what render_shadow_pdf persists."""
        identity = _qde_shadow_identity(_document())
        expected = _expected_shadow_axes("waybill")
        for field, value in expected.items():
            self.assertEqual(value, identity[field], msg=field)

    def test_same_identity_is_paired(self):
        self._create_pair()

        output = self._run()

        self.assertIn("Total pairs: 1", output)
        self.assertIn("[MATCH] doc=doc-pair-1", output)
        self.assertIn("qde_template=warehouse-waybill-ru@2.2.1", output)

    def test_changed_identity_axis_prevents_pairing(self):
        """Changing ANY identity axis on either side yields no pair."""
        cases = (
            ("input_document_id", "shadow", {"document_id": "doc-other"}),
            ("input_revision", "shadow", {"revision": 7}),
            ("input_payload_hash", "shadow", {"payload_hash": "z" * 64}),
            (
                "input_document_contract",
                "shadow",
                {"document_contract": "warehouse.operation-document/v3"},
            ),
            ("shadow_template_id", "shadow", {"template_id": "warehouse-waybill-other"}),
            ("shadow_template_version", "shadow", {"template_version": "1.9.9"}),
            ("shadow_engine", "shadow", {"engine": "qde-other"}),
            ("shadow_engine_version", "shadow", {"engine_version": "0.0.1"}),
            ("shadow_backend", "shadow", {"backend": "other"}),
            ("shadow_backend_version", "shadow", {"backend_version": "0.0.1"}),
            ("legacy_engine", "legacy", {"engine": "other-legacy"}),
            ("legacy_engine_version", "legacy", {"engine_version": "waybill-pdf-v1"}),
            ("legacy_backend", "legacy", {"backend": "other"}),
            ("legacy_backend_version", "legacy", {"backend_version": "0.0.1"}),
            (
                "legacy_document_contract",
                "legacy",
                {"document_contract": "warehouse.operation-document/v3"},
            ),
        )
        for name, side, overrides in cases:
            with self.subTest(case=name):
                RenderedDocumentArtifact.objects.all().delete()
                legacy = _create_legacy_with_axes(
                    document_id="doc-axis", payload_hash="x" * 64
                )
                shadow = _create_shadow_with_axes(
                    document_id="doc-axis", payload_hash="x" * 64
                )
                target = legacy if side == "legacy" else shadow
                for field, value in overrides.items():
                    setattr(target, field, value)
                target.save(update_fields=list(overrides))

                output = self._run()

                self.assertIn("No comparable legacy/shadow pairs found", output)

    def test_legacy_template_label_is_not_a_cross_engine_axis(self):
        """Legacy template_id/version are renderer labels, not pairing axes.

        Legacy persists the document template label (waybill_v1); QDE persists
        the package identity (warehouse-waybill-ru).  They never match, so the
        legacy label must not prune the pair; the current legacy revision is
        pinned by engine/backend/contract instead.
        """
        _create_legacy_with_axes(
            document_id="doc-label",
            payload_hash="l" * 64,
            template_id="waybill_v2",
            template_version="9.9",
        )
        _create_shadow_with_axes(document_id="doc-label", payload_hash="l" * 64)

        output = self._run()

        self.assertIn("Total pairs: 1", output)
        self.assertIn("Skipped non-current revisions: legacy=0 shadow=0", output)

    # -- historical revisions --------------------------------------------

    def test_historical_template_versions_are_not_mixed(self):
        _create_legacy_with_axes(document_id="doc-mix-1", payload_hash="m" * 64)
        _create_shadow_with_axes(
            document_id="doc-mix-1",
            payload_hash="m" * 64,
            template_version="2.2.0",
            filename="documents/pdf/test/mix-stale.pdf",
        )
        _create_shadow_with_axes(
            document_id="doc-mix-1",
            payload_hash="m" * 64,
            filename="documents/pdf/test/mix-current.pdf",
        )

        output = self._run()

        self.assertIn("Total pairs: 1", output)
        self.assertIn("qde_template=warehouse-waybill-ru@2.2.1", output)
        self.assertNotIn("@2.2.0", output)
        self.assertIn("Skipped non-current revisions: legacy=0 shadow=1", output)

    def test_stale_shadow_revision_alone_yields_no_pairs(self):
        _create_legacy_with_axes(document_id="doc-stale-1", payload_hash="s" * 64)
        _create_shadow_with_axes(
            document_id="doc-stale-1",
            payload_hash="s" * 64,
            template_version="2.2.0",
            filename="documents/pdf/test/stale-only.pdf",
        )

        output = self._run()

        self.assertIn("No comparable legacy/shadow pairs found", output)
        self.assertIn("Skipped non-current revisions: legacy=0 shadow=1", output)
        self.assertIn("Unpaired current artifacts: legacy=1 shadow=0", output)

    def test_stale_legacy_revision_alone_yields_no_pairs(self):
        _create_legacy_with_axes(
            document_id="doc-stale-2",
            payload_hash="t" * 64,
            engine_version="waybill-pdf-v1",
            filename="documents/pdf/test/stale-legacy.pdf",
        )
        _create_shadow_with_axes(document_id="doc-stale-2", payload_hash="t" * 64)

        output = self._run()

        self.assertIn("No comparable legacy/shadow pairs found", output)
        self.assertIn("Skipped non-current revisions: legacy=1 shadow=0", output)
        self.assertIn("Unpaired current artifacts: legacy=0 shadow=1", output)

    def test_deterministic_selection_with_multiple_historical_rows(self):
        _create_legacy_with_axes(
            document_id="doc-det",
            payload_hash="d" * 64,
            engine_version="waybill-pdf-v1",
            filename="documents/pdf/test/det-legacy-v1.pdf",
        )
        _create_legacy_with_axes(
            document_id="doc-det",
            payload_hash="d" * 64,
            filename="documents/pdf/test/det-legacy-current.pdf",
        )
        _create_shadow_with_axes(
            document_id="doc-det",
            payload_hash="d" * 64,
            template_version="2.2.0",
            filename="documents/pdf/test/det-shadow-220.pdf",
        )
        _create_shadow_with_axes(
            document_id="doc-det",
            payload_hash="d" * 64,
            filename="documents/pdf/test/det-shadow-current.pdf",
        )

        first = self._run()
        second = self._run()

        self.assertEqual(first, second)
        self.assertIn("Total pairs: 1", first)
        self.assertIn("qde_template=warehouse-waybill-ru@2.2.1", first)
        self.assertIn("Skipped non-current revisions: legacy=1 shadow=1", first)

    def test_unpaired_current_shadow_is_reported(self):
        _create_shadow_with_axes(document_id="doc-orphan-1", payload_hash="o" * 64)

        output = self._run()

        self.assertIn("No comparable legacy/shadow pairs found", output)
        self.assertIn("Unpaired current artifacts: legacy=0 shadow=1", output)

    # -- command behaviour -----------------------------------------------

    def test_no_artifacts(self):
        output = self._run()

        self.assertIn("No comparable legacy/shadow pairs found", output)
        self.assertIn(
            "Identity coverage: paired=0 current_legacy=0 current_shadow=0", output
        )

    def test_deterministic_pairing(self):
        self._create_pair()

        output = self._run()

        self.assertIn("doc-pair-1", output)
        self.assertIn("Total pairs: 1", output)

    def test_limit_option(self):
        for i in range(5):
            self._create_pair(
                document_id=f"doc-limit-{i}",
                payload_hash=f"{i:064d}",
            )

        output = self._run(limit=2)

        self.assertIn("Total pairs: 2", output)

    def test_output_ratios(self):
        self._create_pair(document_id="doc-ratio-1", payload_hash="b" * 64)

        output = self._run()

        self.assertIn("Structural match ratio", output)

    def test_read_only(self):
        self._create_pair(document_id="doc-ro-1", payload_hash="c" * 64)
        count_before = RenderedDocumentArtifact.objects.count()

        self._run()

        count_after = RenderedDocumentArtifact.objects.count()
        self.assertEqual(count_before, count_after)

    def test_mismatched_pdfs_detected(self):
        self._create_pair(
            document_id="doc-mismatch-1",
            payload_hash="e" * 64,
            shadow_pdf=PDF_TWO_PAGES,
        )

        output = self._run()

        self.assertIn("MISMATCH", output)

    def test_different_sha_same_structural_is_match(self):
        """Different SHA but same pages + MediaBox → MATCH.

        Different PDF engines (Typst vs WeasyPrint) produce different byte
        streams for the same content.  Structural match is the contract.
        """
        self._create_pair(document_id="doc-sha-diff-1", payload_hash="k" * 64)

        output = self._run()

        self.assertIn("[MATCH]", output)
        self.assertNotIn("MISMATCH", output)


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


# ── 8. Shadow artifact cache identity (Phase 6D prerequisite) ────────


class TestShadowArtifactCacheIdentity(TestCase):
    """READY-artifact reuse must respect the full render identity.

    Regression guard: a shadow artifact rendered with an older template
    version (or any other changed render axis) must never be served as a
    cache hit after that axis changes (TZ-QDE_INTEGRATION_READINESS
    §5.3/§5.5). Before the fix, render_shadow_pdf looked artifacts up by
    (document_id, revision, payload_hash, engine, render_role, status) only,
    so a template bump (2.1.0 → 2.2.0) kept serving the old PDF.
    """

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self._settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self._settings.enable()

    def tearDown(self):
        self._settings.disable()
        self.media_dir.cleanup()

    @staticmethod
    def _qde_result(pdf_bytes: bytes) -> SimpleNamespace:
        return SimpleNamespace(
            pdf_bytes=pdf_bytes,
            exit_code=0,
            stderr_message="",
            elapsed_seconds=0.1,
            page_count=None,
        )

    def test_identity_fields_match_model_unique_constraint(self) -> None:
        """Reuse lookup axes must stay equal to the artifact identity axes."""
        constraint_fields: list[str] = []
        for constraint in RenderedDocumentArtifact._meta.constraints:
            if constraint.name == "uniq_rendered_document_artifact_v2":
                constraint_fields = list(constraint.fields)
        self.assertEqual(list(QDE_ARTIFACT_IDENTITY_FIELDS), constraint_fields)

    @patch("apps.documents.services.render_via_qde")
    def test_same_identity_reuses_ready_artifact(self, mock_qde) -> None:
        existing = _create_ready_shadow_for_current_identity()

        result = render_shadow_pdf(_document())

        mock_qde.assert_not_called()
        self.assertIsNotNone(result)
        self.assertEqual(result.artifact.id, existing.id)
        self.assertTrue(result.cache_hit)
        self.assertEqual(result.pdf_bytes, SHADOW_PDF)

    @patch("apps.documents.services.render_via_qde")
    def test_old_template_version_is_not_reused(self, mock_qde) -> None:
        """Defect reproduction: template bump 2.1.0 → 2.2.0 must re-render."""
        old_map = {"waybill": ("warehouse-waybill-ru", "2.1.0")}
        new_map = {"waybill": ("warehouse-waybill-ru", "2.2.0")}

        with override_settings(DOCUMENT_TEMPLATE_MAP=old_map):
            old = _create_ready_shadow_for_current_identity()

        mock_qde.return_value = self._qde_result(DIFFERENT_PDF)
        with override_settings(DOCUMENT_TEMPLATE_MAP=new_map):
            result = render_shadow_pdf(_document())

        mock_qde.assert_called_once()
        self.assertIsNotNone(result)
        self.assertNotEqual(result.artifact.id, old.id)
        self.assertEqual(result.artifact.template_version, "2.2.0")
        self.assertEqual(result.pdf_bytes, DIFFERENT_PDF)
        self.assertFalse(result.cache_hit)

        old.refresh_from_db()
        self.assertEqual(old.template_version, "2.1.0")
        self.assertEqual(old.pdf_sha256, hashlib.sha256(SHADOW_PDF).hexdigest())

    @patch("apps.documents.services.render_via_qde")
    def test_changed_document_contract_is_not_reused(self, mock_qde) -> None:
        """Another render axis: a document_contract change is a new revision."""
        with override_settings(QDE_DOCUMENT_CONTRACT="warehouse.operation-document/v3"):
            old = _create_ready_shadow_for_current_identity()

        mock_qde.return_value = self._qde_result(DIFFERENT_PDF)
        with override_settings(QDE_DOCUMENT_CONTRACT="warehouse.operation-document/v2"):
            result = render_shadow_pdf(_document())

        mock_qde.assert_called_once()
        self.assertIsNotNone(result)
        self.assertNotEqual(result.artifact.id, old.id)
        self.assertEqual(result.artifact.document_contract, "warehouse.operation-document/v2")

    @patch("apps.documents.services.render_via_qde")
    def test_each_identity_axis_change_forces_new_render(self, mock_qde) -> None:
        """Every axis in QDE_ARTIFACT_IDENTITY_FIELDS participates in reuse."""
        for field in QDE_ARTIFACT_IDENTITY_FIELDS:
            with self.subTest(field=field):
                RenderedDocumentArtifact.objects.all().delete()
                mock_qde.reset_mock()
                mock_qde.return_value = self._qde_result(DIFFERENT_PDF)

                identity = _qde_shadow_identity(_document())
                if field == "revision":
                    identity[field] = identity[field] + 1
                elif field == "payload_hash":
                    identity[field] = "b" * 64
                else:
                    identity[field] = f"{identity[field]}-other"
                fields = {key: identity[key] for key in QDE_ARTIFACT_IDENTITY_FIELDS}
                old = _create_artifact_with_pdf(pdf_bytes=SHADOW_PDF, **fields)

                result = render_shadow_pdf(_document())

                mock_qde.assert_called_once()
                self.assertIsNotNone(result)
                self.assertNotEqual(
                    result.artifact.id,
                    old.id,
                    f"changed axis {field!r} must not reuse the old artifact",
                )
