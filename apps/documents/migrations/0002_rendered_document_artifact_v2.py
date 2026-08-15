# Phase 6B: RenderedDocumentArtifact v2.
#
# Canonical sequence (docs/TZ-QDE_INTEGRATION_READINESS.md §5.6):
#   A. ADD new identity/role columns (nullable initially);
#   B. DROP the legacy unique constraint and its index BEFORE the rename:
#      on backends that rebuild the table (e.g. SQLite _remake_table) the
#      state must not reference template_name after the rename;
#   C. RENAME template_name -> template_id (DB-level rename, no data loss);
#   D. DATA migration: backfill legacy rows with DEFAULT_LEGACY_AXES
#      (engine_version from row.renderer_version when present);
#   E. ALTER columns NOT NULL after backfill;
#   F. ADD uniq_rendered_document_artifact_v2 (canonical identity axes)
#      and the v2 indexes;
#   G. renderer_version is KEPT as deprecated legacy forensic alias.
#
# Constants are self-contained: the migration never imports mutable runtime
# settings or current model code (deterministic historical-apps pattern).

from django.db import migrations, models

# Canonical legacy defaults (TZ §5.2). template_id/template_version of existing
# rows are NOT overwritten: they are preserved from the rename/current values.
# DEFAULT_LEGACY_AXES values for those two axes apply only to newly created
# rows in service code.
DEFAULT_LEGACY_AXES = {
    "engine": "django-legacy",
    "engine_version": "waybill-pdf-v3",  # fallback if row.renderer_version is empty
    "backend": "weasyprint",
    # Actual Warehouse_web legacy WeasyPrint version: requirements.txt pins
    # weasyprint>=66,<67; the dev/stand image installs 66.0.
    "backend_version": "66.0",
    "document_contract": "warehouse.operation-document/v2",
    "template_id": "waybill_v1",         # legacy template_name value
    "template_version": "1.0",           # legacy template_version value
    "layout_version": "layout-v7.1",     # legacy WAYBILL_LAYOUT_CACHE_VERSION
    "render_role": "legacy",
}

# New v2 columns that get backfilled for existing rows. template_id and
# template_version are excluded on purpose: their historical values must
# survive (template_name -> template_id rename + preserved template_version).
_BACKFILL_FIELDS = (
    "document_contract",
    "engine",
    "engine_version",
    "backend",
    "backend_version",
    "layout_version",
    "render_role",
)


def backfill_legacy_axes(apps, schema_editor):
    Artifact = apps.get_model("documents", "RenderedDocumentArtifact")
    for row in Artifact.objects.all().iterator():
        row.document_contract = DEFAULT_LEGACY_AXES["document_contract"]
        row.engine = DEFAULT_LEGACY_AXES["engine"]
        # engine_version: historical renderer_version wins; fallback otherwise.
        # This preserves real historical renderer versions (TZ §5.6 step 3).
        row.engine_version = row.renderer_version or DEFAULT_LEGACY_AXES["engine_version"]
        row.backend = DEFAULT_LEGACY_AXES["backend"]
        row.backend_version = DEFAULT_LEGACY_AXES["backend_version"]
        row.layout_version = DEFAULT_LEGACY_AXES["layout_version"]
        row.render_role = DEFAULT_LEGACY_AXES["render_role"]
        row.save(update_fields=list(_BACKFILL_FIELDS))


def noop_reverse_legacy_axes(apps, schema_editor):
    # Reverse is handled by schema operations: new v2 columns are dropped,
    # template_id is renamed back to template_name. renderer_version was never
    # modified, so legacy rows remain readable by the old model state.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0001_initial"),
    ]

    operations = [
        # A. Add new columns (nullable initially, backfilled in step D).
        migrations.AddField(
            model_name="rendereddocumentartifact",
            name="document_contract",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="rendereddocumentartifact",
            name="engine",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="rendereddocumentartifact",
            name="engine_version",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="rendereddocumentartifact",
            name="backend",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="rendereddocumentartifact",
            name="backend_version",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="rendereddocumentartifact",
            name="layout_version",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="rendereddocumentartifact",
            name="render_role",
            field=models.CharField(max_length=32, null=True),
        ),
        # B. Drop legacy constraint/index before the rename.
        migrations.RemoveConstraint(
            model_name="rendereddocumentartifact",
            name="uniq_rendered_document_artifact",
        ),
        migrations.RemoveIndex(
            model_name="rendereddocumentartifact",
            name="documents_r_rendere_567470_idx",
        ),
        # C. Real DB/state rename, no data loss.
        migrations.RenameField(
            model_name="rendereddocumentartifact",
            old_name="template_name",
            new_name="template_id",
        ),
        # D. Backfill legacy rows.
        migrations.RunPython(backfill_legacy_axes, noop_reverse_legacy_axes),
        # E. Required v2 columns become NOT NULL after backfill.
        migrations.AlterField(
            model_name="rendereddocumentartifact",
            name="document_contract",
            field=models.CharField(max_length=64),
        ),
        migrations.AlterField(
            model_name="rendereddocumentartifact",
            name="engine",
            field=models.CharField(max_length=32),
        ),
        migrations.AlterField(
            model_name="rendereddocumentartifact",
            name="engine_version",
            field=models.CharField(max_length=32),
        ),
        migrations.AlterField(
            model_name="rendereddocumentartifact",
            name="backend",
            field=models.CharField(max_length=32),
        ),
        migrations.AlterField(
            model_name="rendereddocumentartifact",
            name="backend_version",
            field=models.CharField(max_length=32),
        ),
        migrations.AlterField(
            model_name="rendereddocumentartifact",
            name="layout_version",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AlterField(
            model_name="rendereddocumentartifact",
            name="render_role",
            field=models.CharField(
                choices=[
                    ("primary", "Primary"),
                    ("shadow", "Shadow"),
                    ("emergency_fallback", "Emergency Fallback"),
                    ("legacy", "Legacy"),
                ],
                default="primary",
                max_length=32,
            ),
        ),
        # F. Add the canonical v2 unique constraint and indexes.
        migrations.AddConstraint(
            model_name="rendereddocumentartifact",
            constraint=models.UniqueConstraint(
                fields=(
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
                ),
                name="uniq_rendered_document_artifact_v2",
            ),
        ),
        migrations.AddIndex(
            model_name="rendereddocumentartifact",
            index=models.Index(
                fields=["engine", "backend", "status"],
                name="documents_r_engine_bck_st_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="rendereddocumentartifact",
            index=models.Index(
                fields=["template_id", "template_version"],
                name="documents_r_tmpl_id_ver_idx",
            ),
        ),
    ]
