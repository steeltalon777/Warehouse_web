from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.users.models import SyncStatus, SyncUserBinding
from apps.users.services import UserSyncService


class Command(BaseCommand):
    help = "Repair SyncServer bindings from remote sync-state."

    def add_arguments(self, parser):
        parser.add_argument("--username", dest="username")
        parser.add_argument("--all-failed", action="store_true", dest="all_failed")

    def handle(self, *args, **options):
        username = options.get("username")
        all_failed = bool(options.get("all_failed"))

        if not username and not all_failed:
            raise CommandError("Use --username <name> or --all-failed.")

        queryset = SyncUserBinding.objects.select_related("user")
        if username:
            queryset = queryset.filter(user__username=username)
        else:
            queryset = queryset.filter(
                sync_status__in=[SyncStatus.SYNC_FAILED, SyncStatus.REPAIR_REQUIRED, SyncStatus.MANUAL_OVERRIDE]
            )

        bindings = list(queryset)
        if not bindings:
            self.stdout.write(self.style.WARNING("No matching SyncUserBinding records found."))
            return

        service = UserSyncService()
        repaired = 0
        failed = 0

        for binding in bindings:
            try:
                service.repair_binding_from_remote(user=binding.user, binding=binding)
                repaired += 1
                self.stdout.write(self.style.SUCCESS(f"Repaired {binding.user.username}"))
            except Exception as exc:
                failed += 1
                service.mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
                self.stdout.write(self.style.ERROR(f"Failed {binding.user.username}: {exc}"))

        self.stdout.write(f"Done. repaired={repaired}, failed={failed}")
