from django.db import models


class RenderedDocumentArtifact(models.Model):
    """Technical cache of PDFs rendered by Django from SyncServer document payloads."""

    class Status(models.TextChoices):
        RENDERING = "rendering", "Rendering"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    document_id = models.CharField(max_length=64, db_index=True)
    revision = models.PositiveIntegerField(default=0)
    document_type = models.CharField(max_length=64)
    payload_hash = models.CharField(max_length=64)
    template_name = models.CharField(max_length=128)
    template_version = models.CharField(max_length=32, blank=True)
    renderer_version = models.CharField(max_length=64)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RENDERING)
    pdf_file = models.FileField(upload_to="documents/pdf/", blank=True, null=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    rendered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "document_id",
                    "revision",
                    "payload_hash",
                    "template_name",
                    "template_version",
                    "renderer_version",
                ],
                name="uniq_rendered_document_artifact",
            )
        ]
        indexes = [
            models.Index(fields=["document_id", "status"]),
            models.Index(fields=["renderer_version", "status"]),
        ]

    @property
    def is_ready(self) -> bool:
        return self.status == self.Status.READY and bool(self.pdf_file)

    def __str__(self) -> str:
        return f"RenderedDocumentArtifact(document_id={self.document_id}, status={self.status})"
