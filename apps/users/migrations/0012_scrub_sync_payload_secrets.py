from django.db import migrations
from apps.sync_client.redaction import sanitize_payload


def scrub_payloads(apps, schema_editor):
    SyncUserBinding = apps.get_model("users", "SyncUserBinding")
    SyncDeviceBinding = apps.get_model("users", "SyncDeviceBinding")
    for binding in SyncUserBinding.objects.all():
        if binding.last_sync_payload:
            binding.last_sync_payload = sanitize_payload(
                binding.last_sync_payload
            )
            binding.save(update_fields=["last_sync_payload"])
    for binding in SyncDeviceBinding.objects.all():
        if binding.last_sync_payload:
            binding.last_sync_payload = sanitize_payload(
                binding.last_sync_payload
            )
            binding.save(update_fields=["last_sync_payload"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_add_device_status_fields"),
    ]

    operations = [
        migrations.RunPython(scrub_payloads, noop_reverse),
    ]
