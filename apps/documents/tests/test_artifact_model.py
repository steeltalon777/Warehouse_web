"""RenderedDocumentArtifact v2 model tests (TZ-QDE_INTEGRATION_READINESS §5, §9)."""

from __future__ import annotations

from django.db import IntegrityError, models, transaction
from django.test import TestCase

from apps.documents.models import RenderedDocumentArtifact

CANONICAL_IDENTITY_FIELDS = [
    "document_id",
    "revision",
    "payload_hash",
    "document_contract",
    "template_id",
    "template_version",
    "engine",
    "engine_version",
    "backend",
    "backend_version",
]


def _identity(**overrides) -> dict:
    values = {
        "document_id": "doc-1",
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
    }
    values.update(overrides)
    return values


def _create(**overrides) -> RenderedDocumentArtifact:
    return RenderedDocumentArtifact.objects.create(**_identity(**overrides))


class ArtifactModelFieldTests(TestCase):
    def test_required_v2_fields_exist(self) -> None:
        expected = [
            "document_id",
            "revision",
            "document_type",
            "payload_hash",
            "document_contract",
            "template_id",
            "template_version",
            "engine",
            "engine_version",
            "backend",
            "backend_version",
            "status",
            "render_role",
            "pdf_file",
            "pdf_sha256",
            "size_bytes",
            "rendered_at",
            "last_error",
            "layout_version",
            "renderer_version",
            "created_at",
            "updated_at",
        ]
        model_fields = {field.name for field in RenderedDocumentArtifact._meta.get_fields()}
        for name in expected:
            self.assertIn(name, model_fields, f"missing model field {name!r}")

    def test_status_choices_are_exactly_render_taxonomy(self) -> None:
        self.assertEqual(
            RenderedDocumentArtifact.Status.values,
            ["rendering", "ready", "failed"],
        )
        self.assertEqual(
            RenderedDocumentArtifact.Status.choices,
            [("rendering", "Rendering"), ("ready", "Ready"), ("failed", "Failed")],
        )

    def test_render_role_choices_are_correct(self) -> None:
        field = RenderedDocumentArtifact._meta.get_field("render_role")
        self.assertEqual(
            field.choices,
            [
                ("primary", "Primary"),
                ("shadow", "Shadow"),
                ("emergency_fallback", "Emergency Fallback"),
                ("legacy", "Legacy"),
            ],
        )

    def test_layout_version_is_diagnostic_only(self) -> None:
        field = RenderedDocumentArtifact._meta.get_field("layout_version")
        self.assertTrue(field.blank)

    def test_renderer_version_kept_as_legacy_alias(self) -> None:
        field = RenderedDocumentArtifact._meta.get_field("renderer_version")
        self.assertEqual(field.max_length, 64)


class ArtifactConstraintTests(TestCase):
    def _v2_constraint(self) -> models.UniqueConstraint:
        for constraint in RenderedDocumentArtifact._meta.constraints:
            if constraint.name == "uniq_rendered_document_artifact_v2":
                return constraint
        self.fail("uniq_rendered_document_artifact_v2 constraint not found")
        raise AssertionError  # unreachable

    def test_unique_constraint_is_named_v2(self) -> None:
        self.assertIn(
            "uniq_rendered_document_artifact_v2",
            [c.name for c in RenderedDocumentArtifact._meta.constraints],
        )

    def test_constraint_has_exactly_canonical_identity_axes(self) -> None:
        constraint = self._v2_constraint()
        self.assertEqual(list(constraint.fields), CANONICAL_IDENTITY_FIELDS)

    def test_layout_version_not_in_constraint(self) -> None:
        constraint = self._v2_constraint()
        self.assertNotIn("layout_version", constraint.fields)

    def test_render_role_not_in_constraint(self) -> None:
        constraint = self._v2_constraint()
        self.assertNotIn("render_role", constraint.fields)

    def test_status_not_in_constraint(self) -> None:
        constraint = self._v2_constraint()
        self.assertNotIn("status", constraint.fields)

    def test_duplicate_same_identity_raises_integrity_error(self) -> None:
        _create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            _create()

    def test_changing_each_identity_axis_allows_new_row(self) -> None:
        for field in CANONICAL_IDENTITY_FIELDS:
            with self.subTest(field=field):
                _create()
                base = _identity()
                if field == "revision":
                    base[field] = 1
                elif field == "payload_hash":
                    base[field] = "b" * 64
                else:
                    base[field] = f"{base[field]}-other"
                RenderedDocumentArtifact.objects.create(**base)
                self.assertEqual(
                    RenderedDocumentArtifact.objects.count(),
                    2,
                    f"changing identity axis {field!r} must create a new row",
                )
                RenderedDocumentArtifact.objects.all().delete()

    def test_render_role_change_does_not_create_new_row(self) -> None:
        artifact = _create()
        with transaction.atomic():
            artifact.render_role = "legacy"
            artifact.save()
        self.assertEqual(RenderedDocumentArtifact.objects.count(), 1)

    def test_layout_version_change_does_not_create_new_row(self) -> None:
        artifact = _create()
        with transaction.atomic():
            artifact.layout_version = "layout-v9"
            artifact.save()
        self.assertEqual(RenderedDocumentArtifact.objects.count(), 1)

    def test_status_transition_same_row_allowed(self) -> None:
        artifact = _create(status=RenderedDocumentArtifact.Status.FAILED)
        artifact.status = RenderedDocumentArtifact.Status.RENDERING
        artifact.save()
        artifact.status = RenderedDocumentArtifact.Status.READY
        artifact.save()
        self.assertEqual(RenderedDocumentArtifact.objects.count(), 1)


class ArtifactSemanticsTests(TestCase):
    def test_is_ready_requires_ready_status_and_pdf(self) -> None:
        artifact = _create(status=RenderedDocumentArtifact.Status.READY)
        self.assertFalse(artifact.is_ready)  # no pdf_file yet

        artifact.pdf_file = "documents/pdf/sample.pdf"
        artifact.save()
        artifact.refresh_from_db()
        self.assertTrue(artifact.is_ready)

    def test_failed_artifact_is_not_ready(self) -> None:
        artifact = _create(status=RenderedDocumentArtifact.Status.FAILED, last_error="boom")
        artifact.pdf_file = "documents/pdf/sample.pdf"
        artifact.save()
        self.assertFalse(artifact.is_ready)

    def _identity_lookup(self, **overrides) -> dict:
        """Identity-only lookup kwargs: status/render_role are NOT identity axes."""
        identity = _identity(**overrides)
        for non_identity in ("status", "render_role"):
            identity.pop(non_identity, None)
        return identity

    def test_ready_artifact_immutable_by_get_or_create_semantics(self) -> None:
        """get_or_create on a READY row must return it untouched (no overwrite)."""
        artifact = _create(
            status=RenderedDocumentArtifact.Status.READY,
            pdf_sha256="s" * 64,
            size_bytes=123,
            render_role="shadow",
        )
        existing, created = RenderedDocumentArtifact.objects.get_or_create(
            **self._identity_lookup(),
            defaults={
                "document_type": "waybill",
                "status": RenderedDocumentArtifact.Status.RENDERING,
                "render_role": "primary",
            },
        )
        self.assertFalse(created)
        self.assertEqual(existing.id, artifact.id)
        existing.refresh_from_db()
        self.assertEqual(existing.status, RenderedDocumentArtifact.Status.READY)
        self.assertEqual(existing.pdf_sha256, "s" * 64)
        self.assertEqual(existing.size_bytes, 123)
        self.assertEqual(existing.render_role, "shadow")

    def test_retry_failed_row_allowed(self) -> None:
        artifact = _create(
            status=RenderedDocumentArtifact.Status.FAILED,
            last_error="temporary failure",
            render_role="primary",
        )
        existing, created = RenderedDocumentArtifact.objects.get_or_create(
            **self._identity_lookup(),
            defaults={
                "document_type": "waybill",
                "status": RenderedDocumentArtifact.Status.RENDERING,
                "render_role": "primary",
            },
        )
        self.assertFalse(created)
        self.assertEqual(existing.id, artifact.id)
        existing.status = RenderedDocumentArtifact.Status.READY
        existing.pdf_file = "documents/pdf/retried.pdf"
        existing.save()
        existing.refresh_from_db()
        self.assertTrue(existing.is_ready)
        self.assertEqual(existing.render_role, "primary")
