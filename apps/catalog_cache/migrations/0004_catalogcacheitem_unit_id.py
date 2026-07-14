from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog_cache', '0003_make_optional_string_fields_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='catalogcacheitem',
            name='unit_id',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddIndex(
            model_name='catalogcacheitem',
            index=models.Index(fields=['unit_id'], name='catalog_cache_unit_idx'),
        ),
    ]
