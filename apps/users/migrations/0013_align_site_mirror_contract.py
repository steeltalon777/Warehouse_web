from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0012_scrub_sync_payload_secrets"),
    ]

    operations = [
        migrations.AlterField(
            model_name="site",
            name="name",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="site",
            name="code",
            field=models.CharField(max_length=64, unique=True),
        ),
    ]
