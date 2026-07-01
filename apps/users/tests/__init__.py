from django.contrib import admin
from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from django.urls import reverse
from io import StringIO
from unittest.mock import MagicMock, patch
import uuid as uuid_module

from django.core.management import call_command
from django.db import IntegrityError

from apps.users.admin_forms import SyncManagedDeviceAdminForm
from apps.sync_client.session_auth import store_syncserver_identity
from apps.users.admin import SyncManagedUserAdmin
from apps.users.simple_sync_signals import on_user_logged_in
from apps.users.models import SyncDeviceBinding, SyncStatus, SyncUserBinding


class LogoutViewTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="logout-user",
            password="test-pass-123",
        )

    def test_logout_allows_get_requests(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("users:logout"))

        self.assertRedirects(response, settings.LOGOUT_REDIRECT_URL)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_allows_post_requests(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(reverse("users:logout"))

        self.assertRedirects(response, settings.LOGOUT_REDIRECT_URL)
        self.assertNotIn("_auth_user_id", self.client.session)


class SyncManagedUserAdminTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.admin_user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-pass-123",
        )
        self.managed_user = get_user_model().objects.create_user(
            username="managed-user",
            email="managed@example.com",
            password="test-pass-123",
        )

    def test_get_form_includes_custom_fields(self) -> None:
        request = self.factory.get("/admin/auth/user/1/change/")
        request.user = self.admin_user

        admin_instance = SyncManagedUserAdmin(get_user_model(), admin.site)

        with patch("apps.users.admin.UserSyncService") as mock_service:
            mock_service.return_value.list_sites.return_value = [
                {"site_id": "7", "name": "Main Warehouse", "is_active": True}
            ]

            form_class = admin_instance.get_form(request, obj=self.managed_user, change=True)

        self.assertIn("password_confirm", form_class.base_fields)
        self.assertIn("full_name", form_class.base_fields)
        self.assertIn("sync_role", form_class.base_fields)
        self.assertIn("site_ids", form_class.base_fields)
        self.assertIn("sync_user_token", form_class.base_fields)

    def test_get_form_for_superuser_uses_default_admin_fieldset(self) -> None:
        request = self.factory.get(f"/admin/auth/user/{self.admin_user.pk}/change/")
        request.user = self.admin_user

        admin_instance = SyncManagedUserAdmin(get_user_model(), admin.site)

        fieldsets = admin_instance.get_fieldsets(request, obj=self.admin_user)
        self.assertEqual(fieldsets, admin_instance.superuser_fieldsets)

        form_class = admin_instance.get_form(request, obj=self.admin_user, change=True)

        self.assertIn("username", form_class.base_fields)
        self.assertIn("email", form_class.base_fields)
        self.assertIn("is_superuser", form_class.base_fields)
        self.assertNotIn("password_confirm", form_class.base_fields)
        self.assertNotIn("sync_role", form_class.base_fields)


class SessionAuthTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.root_user = get_user_model().objects.create_superuser(
            username="root-user",
            email="root@example.com",
            password="test-pass-123",
        )

    @staticmethod
    def _attach_session(request) -> None:
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

    @override_settings(SYNC_ROOT_USER_TOKEN="root-env-token")
    @patch("apps.sync_client.session_auth.get_auth_api")
    def test_superuser_stores_root_env_token_when_context_has_no_token(self, mock_get_auth_api) -> None:
        request = self.factory.get("/users/sync/identity/")
        request.user = self.root_user
        self._attach_session(request)

        mock_get_auth_api.return_value.get_context.return_value = {
            "user": {
                "id": "sync-root-id",
                "username": "root-user",
                "role": "root",
                "is_root": True,
            },
            "role": "root",
            "is_root": True,
            "default_site": {
                "site_id": 7,
                "name": "Main Warehouse",
            },
            "available_sites": [
                {
                    "site_id": 7,
                    "name": "Main Warehouse",
                    "permissions": {"can_view": True, "can_operate": True, "can_manage_catalog": True},
                }
            ],
        }

        identity = store_syncserver_identity(request)

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.user_token, "root-env-token")
        self.assertEqual(identity.user_id, "sync-root-id")
        self.assertEqual(identity.role, "root")
        self.assertTrue(identity.is_root)
        self.assertEqual(identity.site_id, 7)
        self.assertEqual(len(identity.available_sites), 1)
        self.assertEqual(identity.available_sites[0]["id"], 7)
        self.assertEqual(request.session["sync_user_token"], "root-env-token")
        self.assertEqual(request.session["sync_default_site_id"], 7)

    @patch("apps.users.simple_sync_signals.store_syncserver_identity")
    def test_login_signal_sets_request_user_before_sync_identity_fetch(self, mock_store_identity) -> None:
        request = self.factory.post("/login/")
        self._attach_session(request)

        on_user_logged_in(sender=get_user_model(), request=request, user=self.root_user)

        self.assertEqual(request.user, self.root_user)
        mock_store_identity.assert_called_once_with(request)


class SyncManagedDeviceAdminFormTests(TestCase):
    def test_new_binding_form_includes_readonly_sync_device_token(self) -> None:
        form = SyncManagedDeviceAdminForm(instance=SyncDeviceBinding())

        self.assertIn("sync_device_token", form.fields)
        self.assertEqual(form.fields["sync_device_token"].initial, "")


class SyncDeviceBindingAdminTests(TestCase):
    def setUp(self) -> None:
        self.admin_user = get_user_model().objects.create_superuser(
            username="device-admin",
            email="device-admin@example.com",
            password="test-pass-123",
        )
        self.client.force_login(self.admin_user)

    def test_add_view_renders(self) -> None:
        response = self.client.get(reverse("admin:users_syncdevicebinding_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sync_device_token")

    @patch("apps.users.admin.DeviceSyncService")
    def test_add_view_creates_binding_and_syncs_device(self, mock_service) -> None:
        response = self.client.post(
            reverse("admin:users_syncdevicebinding_add"),
            {
                "device_code": "DJANGO_WEB",
                "device_name": "Django Web Client",
                "is_active": "on",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SyncDeviceBinding.objects.count(), 1)
        binding = SyncDeviceBinding.objects.get()
        self.assertEqual(binding.device_code, "DJANGO_WEB")
        self.assertEqual(binding.device_name, "Django Web Client")
        mock_service.return_value.create_binding.assert_called_once()

    @patch("apps.users.admin.DeviceSyncService")
    def test_change_view_updates_binding_and_syncs_device(self, mock_service) -> None:
        binding = SyncDeviceBinding.objects.create(
            device_code="DJANGO_WEB",
            device_name="Django Web Client",
            syncserver_device_id=11,
            sync_device_token="device-token",
            is_active=True,
        )

        response = self.client.post(
            reverse("admin:users_syncdevicebinding_change", args=[binding.pk]),
            {
                "device_code": "DJANGO_DESKTOP",
                "device_name": "Django Desktop Client",
                "is_active": "on",
                "sync_device_token": "device-token",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        binding.refresh_from_db()
        self.assertEqual(binding.device_code, "DJANGO_DESKTOP")
        self.assertEqual(binding.device_name, "Django Desktop Client")
        mock_service.return_value.sync_existing_binding.assert_called_once()

    @patch("apps.users.admin.DeviceSyncService")
    def test_sync_action_calls_sync_service(self, mock_service) -> None:
        binding = SyncDeviceBinding.objects.create(
            device_code="DJANGO_WEB",
            device_name="Django Web Client",
            syncserver_device_id=11,
            is_active=True,
        )

        response = self.client.post(reverse("admin:users_syncdevicebinding_sync", args=[binding.pk]))

        self.assertEqual(response.status_code, 302)
        mock_service.return_value.sync_existing_binding.assert_called_once_with(binding=binding)

    @patch("apps.users.admin.DeviceSyncService")
    def test_rotate_token_action_calls_rotate_and_apply(self, mock_service) -> None:
        binding = SyncDeviceBinding.objects.create(
            device_code="DJANGO_WEB",
            device_name="Django Web Client",
            syncserver_device_id=11,
            is_active=True,
        )
        mock_service.return_value.rotate_token.return_value = {"device_token": "rotated-token"}

        response = self.client.post(reverse("admin:users_syncdevicebinding_rotate_token", args=[binding.pk]))

        self.assertEqual(response.status_code, 302)
        mock_service.return_value.rotate_token.assert_called_once_with(11)
        mock_service.return_value.apply_rotated_token.assert_called_once()

    @patch("apps.users.admin.DeviceSyncService")
    def test_repair_action_calls_repair_service(self, mock_service) -> None:
        binding = SyncDeviceBinding.objects.create(
            device_code="DJANGO_WEB",
            device_name="Django Web Client",
            syncserver_device_id=11,
            is_active=True,
        )

        response = self.client.post(reverse("admin:users_syncdevicebinding_repair", args=[binding.pk]))

        self.assertEqual(response.status_code, 302)
        mock_service.return_value.repair_binding_from_remote.assert_called_once_with(binding=binding)


class ImportSyncUsersTests(TestCase):
    """Tests for the import_sync_users management command."""

    MOCK_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
    MOCK_USERNAME = "remote_user"

    @staticmethod
    def _default_users_response():
        return [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "username": "remote_user",
                "email": "remote@example.com",
                "full_name": "Remote User",
                "is_active": True,
                "is_root": False,
                "role": "storekeeper",
                "default_site_id": 7,
            }
        ]

    @staticmethod
    def _mock_client(users_list=None):
        if users_list is None:
            users_list = ImportSyncUsersTests._default_users_response()

        def mock_get(path, *, params=None):
            if "sync-state" in path:
                parts = path.strip("/").split("/")
                uid = parts[2]
                return {
                    "user": {"id": uid, "user_token": "tok_internal_value"},
                    "scopes": [{"site_id": 7}],
                }
            return {"users": users_list, "total_count": len(users_list)}

        mock_client = MagicMock()
        mock_client.get.side_effect = mock_get
        return mock_client

    def test_dry_run_creates_no_db_records(self) -> None:
        mock_client = self._mock_client()
        with patch(
            "apps.users.management.commands.import_sync_users.SyncServerRootAdminClient",
            return_value=mock_client,
        ):
            call_command("import_sync_users", "--dry-run")
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(SyncUserBinding.objects.count(), 0)

    def test_apply_creates_user_and_binding(self) -> None:
        mock_client = self._mock_client()
        with patch(
            "apps.users.management.commands.import_sync_users.SyncServerRootAdminClient",
            return_value=mock_client,
        ):
            call_command("import_sync_users", "--apply")
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(SyncUserBinding.objects.count(), 1)
        user = get_user_model().objects.get()
        binding = SyncUserBinding.objects.get()
        self.assertEqual(user.username, self.MOCK_USERNAME)
        self.assertEqual(str(binding.syncserver_user_id), self.MOCK_USER_ID)
        self.assertEqual(binding.sync_role, "storekeeper")
        self.assertEqual(binding.default_site_id, "7")
        self.assertEqual(binding.site_ids, ["7"])
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.is_active)

    def test_existing_binding_is_updated_not_duplicated(self) -> None:
        user = get_user_model().objects.create_user(username=self.MOCK_USERNAME, password="test123")
        SyncUserBinding.objects.create(
            user=user,
            syncserver_user_id=self.MOCK_USER_ID,
            sync_user_token="old-token",
            sync_role="observer",
            default_site_id="1",
            site_ids=[1],
            sync_status=SyncStatus.SYNCED,
        )

        mock_client = self._mock_client()
        with patch(
            "apps.users.management.commands.import_sync_users.SyncServerRootAdminClient",
            return_value=mock_client,
        ):
            call_command("import_sync_users", "--apply")

        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(SyncUserBinding.objects.count(), 1)
        binding = SyncUserBinding.objects.get()
        self.assertEqual(binding.sync_role, "storekeeper")
        self.assertEqual(binding.default_site_id, "7")
        self.assertEqual(binding.site_ids, ["7"])
        self.assertEqual(binding.sync_user_token, "old-token")

    def test_username_conflict_reported(self) -> None:
        other_uuid = "11111111-1111-1111-1111-111111111111"
        user = get_user_model().objects.create_user(username=self.MOCK_USERNAME, password="test123")
        SyncUserBinding.objects.create(
            user=user,
            syncserver_user_id=other_uuid,
            sync_user_token="tok",
            sync_role="storekeeper",
            sync_status=SyncStatus.SYNCED,
        )

        mock_client = self._mock_client()
        err = StringIO()
        with patch(
            "apps.users.management.commands.import_sync_users.SyncServerRootAdminClient",
            return_value=mock_client,
        ):
            call_command("import_sync_users", "--apply", stderr=err)

        self.assertIn("Conflict", err.getvalue())
        self.assertIn(self.MOCK_USERNAME, err.getvalue())
        self.assertEqual(SyncUserBinding.objects.count(), 1)

    def test_no_token_values_in_output(self) -> None:
        mock_client = self._mock_client()
        out = StringIO()
        with patch(
            "apps.users.management.commands.import_sync_users.SyncServerRootAdminClient",
            return_value=mock_client,
        ):
            call_command("import_sync_users", "--dry-run", stdout=out)
        output = out.getvalue()
        self.assertNotIn("tok_", output)
        self.assertNotIn("sync_user_token", output)
        self.assertNotIn("SYNC_ROOT_USER_TOKEN", output)
        self.assertNotIn("SYNC_DEVICE_TOKEN", output)

    def test_create_binding_without_sync_user_token_succeeds(self) -> None:
        user = get_user_model().objects.create_user(username="tokenless", password="test123")
        try:
            binding = SyncUserBinding.objects.create(
                user=user,
                syncserver_user_id=uuid_module.uuid4(),
                sync_role="storekeeper",
                default_site_id="7",
                site_ids=[],
                sync_status=SyncStatus.SYNCED,
            )
            self.assertIsNotNone(binding.pk)
            self.assertIsNone(binding.sync_user_token)
        except IntegrityError:
            self.fail("IntegrityError raised — sync_user_token is still NOT NULL in DB")

    def test_apply_multiple_users(self) -> None:
        users_list = [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "username": "alpha",
                "email": "alpha@example.com",
                "full_name": "Alpha User",
                "is_active": True,
                "is_root": False,
                "role": "storekeeper",
                "default_site_id": 7,
            },
            {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "username": "beta",
                "email": "beta@example.com",
                "full_name": "Beta User",
                "is_active": True,
                "is_root": False,
                "role": "observer",
                "default_site_id": 8,
            },
        ]

        def multi_mock_get(path, *, params=None):
            if "sync-state" in path:
                return {
                    "user": {"id": "mock", "user_token": "tok"},
                    "scopes": [{"site_id": 7}],
                }
            return {"users": users_list, "total_count": len(users_list)}

        mock_client = MagicMock()
        mock_client.get.side_effect = multi_mock_get
        with patch(
            "apps.users.management.commands.import_sync_users.SyncServerRootAdminClient",
            return_value=mock_client,
        ):
            call_command("import_sync_users", "--apply")

        self.assertEqual(get_user_model().objects.count(), 2)
        self.assertEqual(SyncUserBinding.objects.count(), 2)
