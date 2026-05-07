from django.contrib import admin
from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse
from unittest.mock import patch

from apps.users.admin_forms import SyncManagedDeviceAdminForm
from apps.sync_client.session_auth import store_syncserver_identity
from apps.users.admin import SyncManagedUserAdmin
from apps.users.models import SyncDeviceBinding


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
        self.assertIn("default_site_id", form_class.base_fields)
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

    @patch("apps.sync_client.session_auth.get_auth_api")
    def test_store_syncserver_identity_uses_root_token_fallback(self, mock_get_auth_api) -> None:
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

        with self.settings(SYNC_ROOT_USER_TOKEN="root-token-123"):
            identity = store_syncserver_identity(request)

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.user_token, "root-token-123")
        self.assertEqual(identity.user_id, "sync-root-id")
        self.assertEqual(identity.role, "root")
        self.assertTrue(identity.is_root)
        self.assertEqual(identity.site_id, 7)
        self.assertEqual(len(identity.available_sites), 1)
        self.assertEqual(identity.available_sites[0]["id"], 7)
        self.assertEqual(request.session["sync_user_token"], "root-token-123")
        self.assertEqual(request.session["sync_default_site_id"], 7)


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
