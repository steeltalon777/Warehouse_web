# Generated manually for the document PDF artifact cache.

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RenderedDocumentArtifact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_id", models.CharField(db_index=True, max_length=64)),
                ("revision", models.PositiveIntegerField(default=0)),
                ("document_type", models.CharField(max_length=64)),
                ("payload_hash", models.CharField(max_length=64)),
                ("template_name", models.CharField(max_length=128)),
                ("template_version", models.CharField(blank=True, max_length=32)),
                ("renderer_version", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("rendering", "Rendering"), ("ready", "Ready"), ("failed", "Failed")],
                        default="rendering",
                        max_length=16,
                    ),
                ),
                ("pdf_file", models.FileField(blank=True, null=True, upload_to="documents/pdf/")),
                ("pdf_sha256", models.CharField(blank=True, max_length=64)),
                ("size_bytes", models.PositiveIntegerField(default=0)),
                ("rendered_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="rendereddocumentartifact",
            constraint=models.UniqueConstraint(
                fields=(
                    "document_id",
                    "revision",
                    "payload_hash",
                    "template_name",
                    "template_version",
                    "renderer_version",
                ),
                name="uniq_rendered_document_artifact",
            ),
        ),
        migrations.AddIndex(
            model_name="rendereddocumentartifact",
            index=models.Index(fields=["document_id", "status"], name="documents_r_documen_97551f_idx"),
        ),
        migrations.AddIndex(
            model_name="rendereddocumentartifact",
            index=models.Index(fields=["renderer_version", "status"], name="documents_r_rendere_567470_idx"),
        ),
    ]
