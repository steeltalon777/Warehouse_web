from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_syncuserbinding_last_sync_payload_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="site",
            name="description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="site",
            name="syncserver_site_id",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="site",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
