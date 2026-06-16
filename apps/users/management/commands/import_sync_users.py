from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.sync_client.exceptions import SyncBackendUnavailable
from apps.sync_client.root_admin_client import SyncServerRootAdminClient
from apps.users.models import SyncStatus, SyncUserBinding

User = get_user_model()


class Command(BaseCommand):
    help = "Import users from SyncServer into Django auth.User."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", dest="dry_run")
        parser.add_argument("--apply", action="store_true", dest="apply")
        parser.add_argument("--username", dest="username")
        parser.add_argument("--sync-user-id", dest="sync_user_id")
        parser.add_argument("--include-inactive", action="store_true", dest="include_inactive")
        parser.add_argument("--fail-on-conflict", action="store_true", dest="fail_on_conflict")
        parser.add_argument("--limit", type=int, dest="limit")

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False) or not options.get("apply", False)
        username = options.get("username")
        sync_user_id = options.get("sync_user_id")
        include_inactive = options.get("include_inactive", False)
        fail_on_conflict = options.get("fail_on_conflict", False)
        limit = options.get("limit")

        try:
            client = SyncServerRootAdminClient()
        except RuntimeError as e:
            raise CommandError(f"SyncServer client not configured: {e}")

        self.stdout.write("Scanning remote users from SyncServer...")

        try:
            all_remote_users = self._fetch_all_users(client, limit)
        except SyncBackendUnavailable as e:
            raise CommandError(f"SyncServer is unavailable: {e}")

        if username:
            all_remote_users = [u for u in all_remote_users if u.get("username") == username]
            if not all_remote_users:
                self.stderr.write(self.style.WARNING(f"No remote user found with username '{username}'."))
                return

        if sync_user_id:
            all_remote_users = [u for u in all_remote_users if str(u.get("id")) == sync_user_id]
            if not all_remote_users:
                self.stderr.write(self.style.WARNING(f"No remote user found with id '{sync_user_id}'."))
                return

        if not include_inactive:
            all_remote_users = [u for u in all_remote_users if u.get("is_active", True)]

        stats = {
            "scanned": len(all_remote_users),
            "would_create_users": 0,
            "would_create_bindings": 0,
            "would_update_bindings": 0,
            "skipped_synced": 0,
            "conflicts": 0,
            "failures": 0,
        }

        for remote_user in all_remote_users:
            try:
                self._process_user(client, remote_user, dry_run, stats, fail_on_conflict)
            except CommandError:
                raise
            except Exception as exc:
                stats["failures"] += 1
                self.stderr.write(
                    self.style.ERROR(f"Error processing {remote_user.get('username', '?')}: {exc}")
                )

        self._report_stats(stats, dry_run)

        if stats["failures"] > 0:
            raise CommandError("Import completed with failures.")

        if fail_on_conflict and stats["conflicts"] > 0:
            raise CommandError("Import completed with conflicts (--fail-on-conflict).")

    def _fetch_all_users(self, client, limit):
        users = []
        page = 1
        page_size = 100

        while True:
            response = client.get("/admin/users", params={"page": page, "page_size": page_size})
            page_users = response.get("users", [])
            users.extend(page_users)

            if limit and len(users) >= limit:
                return users[:limit]

            if len(page_users) < page_size:
                break

            page += 1

        return users

    def _process_user(self, client, remote_user, dry_run, stats, fail_on_conflict):
        remote_id_str = str(remote_user["id"])
        remote_username = str(remote_user["username"])
        remote_role = str(remote_user.get("role", "storekeeper"))
        remote_default_site_id = str(remote_user.get("default_site_id", ""))

        sync_state = client.get(f"/admin/users/{remote_id_str}/sync-state")
        scopes = sync_state.get("scopes", [])
        site_ids = [str(s.get("site_id")) for s in scopes]

        # Case 1: binding exists by syncserver_user_id
        try:
            binding = SyncUserBinding.objects.get(syncserver_user_id=remote_id_str)
            if self._binding_matches(binding, remote_role, remote_default_site_id, site_ids):
                stats["skipped_synced"] += 1
            else:
                stats["would_update_bindings"] += 1
                if not dry_run:
                    with transaction.atomic():
                        self._apply_binding_update(binding, remote_role, remote_default_site_id, site_ids)
            return
        except SyncUserBinding.DoesNotExist:
            pass

        # Case 2: user exists by username
        try:
            django_user = User.objects.get(username=remote_username)
            existing_binding = SyncUserBinding.objects.filter(user=django_user).first()
            if existing_binding is not None:
                stats["conflicts"] += 1
                msg = (
                    f"Conflict: user '{remote_username}' already bound to "
                    f"SyncServer user {existing_binding.syncserver_user_id}, "
                    f"skipping remote user {remote_id_str}"
                )
                self.stderr.write(self.style.WARNING(msg))
                return

            stats["would_create_bindings"] += 1
            if not dry_run:
                with transaction.atomic():
                    self._apply_binding_create(django_user, remote_id_str, remote_role, remote_default_site_id, site_ids)
            return
        except User.DoesNotExist:
            pass

        # Case 3: create user + binding
        stats["would_create_users"] += 1
        stats["would_create_bindings"] += 1
        if not dry_run:
            with transaction.atomic():
                django_user = self._apply_user_create(remote_user)
                self._apply_binding_create(django_user, remote_id_str, remote_role, remote_default_site_id, site_ids)

    @staticmethod
    def _binding_matches(binding, role, default_site_id, site_ids):
        return (
            binding.sync_role == role
            and str(binding.default_site_id or "") == default_site_id
            and list(binding.site_ids) == site_ids
        )

    @staticmethod
    def _apply_user_create(remote_user):
        user = User(
            username=str(remote_user["username"]),
            email=str(remote_user.get("email", "")),
            first_name=str(remote_user.get("full_name", "")),
            is_active=bool(remote_user.get("is_active", True)),
        )
        user.set_unusable_password()
        user.save()
        return user

    @staticmethod
    def _apply_binding_create(django_user, syncserver_user_id, role, default_site_id, site_ids):
        SyncUserBinding.objects.create(
            user=django_user,
            syncserver_user_id=syncserver_user_id,
            sync_user_token="",
            sync_role=role,
            default_site_id=default_site_id,
            site_ids=site_ids,
            sync_status=SyncStatus.SYNCED,
        )

    @staticmethod
    def _apply_binding_update(binding, role, default_site_id, site_ids):
        binding.sync_role = role
        binding.default_site_id = default_site_id
        binding.site_ids = site_ids
        binding.sync_status = SyncStatus.SYNCED
        binding.save(update_fields=["sync_role", "default_site_id", "site_ids", "sync_status", "updated_at"])

    def _report_stats(self, stats, dry_run):
        label = "would" if dry_run else "did"
        self.stdout.write(f"  remote users scanned: {stats['scanned']}")
        self.stdout.write(f"  {label} create users: {stats['would_create_users']}")
        self.stdout.write(f"  {label} create bindings: {stats['would_create_bindings']}")
        self.stdout.write(f"  {label} update bindings: {stats['would_update_bindings']}")
        self.stdout.write(f"  skipped (already synced): {stats['skipped_synced']}")
        self.stdout.write(f"  conflicts: {stats['conflicts']}")
        self.stdout.write(f"  failures: {stats['failures']}")
