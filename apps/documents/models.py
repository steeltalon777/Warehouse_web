from django.db import models


class RenderedDocumentArtifact(models.Model):
    """Technical cache of PDFs derived from SyncServer document payloads.

    ADR-0030 D3 + ADR-0032 D1: artifact identity is immutable per render-revision.
    Re-render with different engine/backend/contract/template creates a NEW row,
    not an in-place update of existing row.

    Это cache technical state (PDF bytes + cache key fields), не warehouse domain data.
    Хранилище допустимо в Django ORM согласно Warehouse_web AGENTS.md
    («local storage for technical web state: ... cache»).
    """

    class Status(models.TextChoices):
        RENDERING = "rendering", "Rendering"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    # --- Identity: business document (из SyncServer documents.payload) ---
    document_id = models.CharField(max_length=64, db_index=True)
    revision = models.PositiveIntegerField(default=0)
    document_type = models.CharField(max_length=64)

    # --- Identity: render-revision (QDE axes; ADR-0029 §9.3) ---
    # Все обязательные identity axes заполняются для QDE-rendered строк.
    # Legacy-строки (Phase 6D backward compat) получают значения из DEFAULT_LEGACY_AXES.
    payload_hash = models.CharField(max_length=64)
    document_contract = models.CharField(max_length=64)              # e.g. "warehouse.operation-document/v2"
    template_id = models.CharField(max_length=128)                   # e.g. "warehouse-waybill-ru" (renamed from template_name)
    template_version = models.CharField(max_length=32, blank=True)   # e.g. "2.0.0"
    engine = models.CharField(max_length=32)                         # "qde" или "django-legacy"
    engine_version = models.CharField(max_length=32)                 # "0.1.0" / "waybill-pdf-v3"
    backend = models.CharField(max_length=32)                        # "typst" / "weasyprint"
    backend_version = models.CharField(max_length=32)                # "0.15.1" / "66.0"

    # --- Status + content ---
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RENDERING)
    render_role = models.CharField(
        max_length=32,
        choices=[
            ("primary", "Primary"),
            ("shadow", "Shadow"),
            ("emergency_fallback", "Emergency Fallback"),
            ("legacy", "Legacy"),
        ],
        default="primary",
    )
    pdf_file = models.FileField(upload_to="documents/pdf/", blank=True, null=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    rendered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    # Optional diagnostic metadata only. Layout changes that affect output MUST bump template_version.
    # Therefore layout_version is intentionally NOT part of artifact identity/cache key.
    layout_version = models.CharField(max_length=32, blank=True)     # legacy/diagnostic label, e.g. "layout-v7.1"

    # Deprecated legacy forensic alias. Kept in the DB for historical
    # reproducibility; may be removed only in Phase 11+ after full cutover.
    renderer_version = models.CharField(max_length=64)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "document_id", "revision", "payload_hash",
                    "document_contract",
                    "template_id", "template_version",
                    "engine", "engine_version", "backend", "backend_version",
                ],
                name="uniq_rendered_document_artifact_v2",
            ),
        ]
        indexes = [
            models.Index(fields=["document_id", "status"], name="documents_r_documen_97551f_idx"),
            models.Index(fields=["engine", "backend", "status"], name="documents_r_engine_bck_st_idx"),
            models.Index(fields=["template_id", "template_version"], name="documents_r_tmpl_id_ver_idx"),
        ]

    @property
    def is_ready(self) -> bool:
        return self.status == self.Status.READY and bool(self.pdf_file)

    def __str__(self) -> str:
        return (
            f"RenderedDocumentArtifact(document_id={self.document_id}, "
            f"engine={self.engine}, backend={self.backend}, status={self.status})"
        )
