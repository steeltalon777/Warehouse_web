"""Pre-deploy audit for Django Admin hardening. Read-only. No token values in output."""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from apps.users.models import SyncUserBinding, SyncDeviceBinding, Site, SyncStatus
from apps.sync_client.redaction import SENSITIVE_KEYS
from django.db.models import Count

User = get_user_model()

class Command(BaseCommand):
    help = "Pre-deploy security audit for Django Admin hardening"

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=["pre-scrub"], help="Pre-scrub inventory before migration")
        parser.add_argument("--fail-on-findings", action="store_true", help="Exit non-zero if blockers")

    def handle(self, *args, **options):
        findings = []
        findings.extend(self._check_dangerous_staff())
        findings.extend(self._check_non_super_root())
        findings.extend(self._check_payload_keys())
        findings.extend(self._check_sync_status())
        findings.extend(self._check_missing_binding())
        findings.extend(self._check_site_mirror())
        findings.extend(self._check_migrations())

        if options.get("mode") == "pre-scrub":
            self.stdout.write(self.style.WARNING("=== PRE-SCRUB INVENTORY ==="))
            self.stdout.write("(No secret values — only IDs, key paths, counts)")
            for f in findings:
                self.stdout.write(f"  [{f['category']}] {f['message']}")
            self.stdout.write(f"\nTotal: {len(findings)}")
            return

        blockers = [f for f in findings if f.get("severity") == "blocker"]
        warnings = [f for f in findings if f.get("severity") == "warning"]

        if blockers:
            self.stdout.write(self.style.ERROR(f"BLOCKERS ({len(blockers)}):"))
            for b in blockers:
                self.stdout.write(f"  [{b['category']}] {b['message']}")
        if warnings:
            self.stdout.write(self.style.WARNING(f"WARNINGS ({len(warnings)}):"))
            for w in warnings:
                self.stdout.write(f"  [{w['category']}] {w['message']}")
        if not blockers and not warnings:
            self.stdout.write(self.style.SUCCESS("No findings."))

        if options.get("fail_on_findings") and blockers:
            raise SystemExit(1)

    def _check_dangerous_staff(self):
        res = []
        for u in User.objects.filter(is_staff=True, is_superuser=False):
            for perm in ["auth.change_user","auth.add_user","users.change_syncuserbinding","users.change_syncdevicebinding"]:
                if u.has_perm(perm):
                    res.append({"severity":"blocker","category":"dangerous_permissions",
                                "message":f"User '{u.username}' (ID={u.pk}): {perm}"})
        return res

    def _check_non_super_root(self):
        res = []
        for b in SyncUserBinding.objects.filter(sync_role="root"):
            if not b.user.is_superuser:
                res.append({"severity":"blocker","category":"non_super_root",
                            "message":f"Binding ID={b.pk}: non-superuser '{b.user.username}' has sync_role=root"})
        return res

    def _check_payload_keys(self):
        res = []
        for model_cls, name in [(SyncUserBinding,"SyncUserBinding"),(SyncDeviceBinding,"SyncDeviceBinding")]:
            for obj in model_cls.objects.exclude(last_sync_payload={}).exclude(last_sync_payload__isnull=True):
                found = self._find_keys(obj.last_sync_payload)
                if found:
                    res.append({"severity":"blocker","category":"sensitive_keys",
                                "message":f"{name} ID={obj.pk}: sensitive keys={found}"})
        return res

    def _find_keys(self, payload, found=None):
        if found is None: found = set()
        if isinstance(payload, dict):
            for k in payload:
                if any(k.lower() == sk.lower() for sk in SENSITIVE_KEYS):
                    found.add(k)
                self._find_keys(payload[k], found)
        elif isinstance(payload, (list, tuple)):
            for item in payload:
                self._find_keys(item, found)
        return list(found)

    def _check_sync_status(self):
        res = []
        max_age = getattr(settings, "ADMIN_SYNC_PENDING_MAX_AGE_SECONDS", 300)
        now = timezone.now()
        blocker_statuses = [SyncStatus.SYNC_FAILED, SyncStatus.REPAIR_REQUIRED, SyncStatus.MANUAL_OVERRIDE]
        for model_cls, name in [(SyncUserBinding,"SyncUserBinding"),(SyncDeviceBinding,"SyncDeviceBinding")]:
            for obj in model_cls.objects.exclude(sync_status=SyncStatus.SYNCED):
                sev = "blocker" if obj.sync_status in blocker_statuses else "warning"
                if obj.sync_status == SyncStatus.PENDING and obj.last_sync_at:
                    age = (now - obj.last_sync_at).total_seconds()
                    sev = "blocker" if age > max_age else "warning"
                res.append({"severity":sev,"category":"sync_status",
                            "message":f"{name} ID={obj.pk}: status={obj.sync_status}"})
        return res

    def _check_missing_binding(self):
        res = []
        threshold = timezone.now() - timezone.timedelta(days=30)
        for u in User.objects.filter(is_active=True, is_superuser=False, date_joined__gte=threshold):
            try:
                b = u.sync_binding
                if not b.syncserver_user_id:
                    res.append({"severity":"blocker","category":"missing_remote_id",
                                "message":f"User '{u.username}' (ID={u.pk}): no remote ID"})
            except SyncUserBinding.DoesNotExist:
                res.append({"severity":"blocker","category":"missing_binding",
                            "message":f"User '{u.username}' (ID={u.pk}): no binding"})
        return res

    def _check_site_mirror(self):
        res = []
        for dup in Site.objects.values("syncserver_site_id").annotate(c=Count("pk")).filter(c__gt=1, syncserver_site_id__isnull=False):
            res.append({"severity":"blocker","category":"duplicate_site",
                        "message":f"syncserver_site_id '{dup['syncserver_site_id']}' appears {dup['c']}x"})
        for dup in Site.objects.values("code").annotate(c=Count("pk")).filter(c__gt=1):
            res.append({"severity":"warning","category":"duplicate_code",
                        "message":f"code '{dup['code']}' appears {dup['c']}x"})
        return res

    def _check_migrations(self):
        try:
            from django.db.migrations.executor import MigrationExecutor
            from django.db import connections
            executor = MigrationExecutor(connections["default"])
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            return [{"severity":"blocker","category":"pending_migrations",
                     "message":f"Unapplied migrations: {len(plan)}"}] if plan else []
        except Exception as e:
            return [{"severity":"blocker","category":"migration_error","message":str(e)}]
