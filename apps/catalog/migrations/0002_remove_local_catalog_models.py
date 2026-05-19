from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="Item"),
        migrations.DeleteModel(name="Category"),
        migrations.DeleteModel(name="Unit"),
    ]
