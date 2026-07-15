"""Negative security tests for Django Admin hardening (Unit 1A).

Level 2-3: Unit tests for admin authorization, HTTP contract, and permission
boundaries.  DB-backed integration tests for real request/response cycles.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import Role, SyncDeviceBinding, SyncUserBinding, UserProfile

User = get_user_model()


def _make_routes(test_user_pk: int, test_device_pk: int):
    return [
        ("admin:users_user_sync", [test_user_pk], "apps.users.admin.UserSyncService"),
        ("admin:users_user_repair", [test_user_pk], "apps.users.admin.UserSyncService"),
        ("admin:users_user_rotate_token", [test_user_pk], "apps.users.admin.UserSyncService"),
        ("admin:users_syncdevicebinding_sync", [test_device_pk], "apps.users.admin.DeviceSyncService"),
        ("admin:users_syncdevicebinding_repair", [test_device_pk], "apps.users.admin.DeviceSyncService"),
        ("admin:users_syncdevicebinding_rotate_token", [test_device_pk], "apps.users.admin.DeviceSyncService"),
    ]


class AdminCustomRoutesSecurityTests(TestCase):
    """Test matrix for all six custom admin routes (sync, repair, rotate-token)."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="sec_super", password="pass12345", is_active=True,
        )
        self.inactive_superuser = User.objects.create_superuser(
            username="sec_inactive", password="pass12345", is_active=False,
        )
        self.staff_user = User.objects.create_user(
            username="sec_staff", password="pass12345",
            is_staff=True, is_superuser=False, is_active=True,
        )

        self.test_user = User.objects.create_user(
            username="sec_target", password="pass12345",
        )
        self.test_binding = SyncUserBinding.objects.create(
            user=self.test_user, sync_role=Role.STOREKEEPER,
        )
        self.test_device = SyncDeviceBinding.objects.create(
            device_code="SEC-DEV-001", device_name="Security Test Device",
        )

        self.routes = _make_routes(self.test_user.pk, self.test_device.pk)
        self.missing_pk = 999999

    # ── Anonymous ──────────────────────────────────────────────

    def test_anonymous_get_redirects_to_login(self):
        for name, args, _ in self.routes:
            with self.subTest(route=name):
                url = reverse(name, args=args)
                response = self.client.get(url)
                self.assertIn(response.status_code, (302,))

    def test_anonymous_post_redirects_to_login(self):
        for name, args, _ in self.routes:
            with self.subTest(route=name):
                url = reverse(name, args=args)
                response = self.client.post(url, {})
                self.assertIn(response.status_code, (302,))

    # ── Inactive superuser ────────────────────────────────────

    def test_inactive_superuser_denied(self):
        for name, args, svc_path in self.routes:
            with self.subTest(route=name):
                self.client.force_login(self.inactive_superuser)
                url = reverse(name, args=args)
                with patch(svc_path) as mock_svc:
                    response = self.client.post(url, {})
                    self.assertIn(response.status_code, (302, 403))
                    mock_svc.assert_not_called()

    # ── GET / HEAD → 405 ──────────────────────────────────────

    def test_get_returns_405_with_allow_header(self):
        for name, args, _ in self.routes:
            with self.subTest(route=name):
                self.client.force_login(self.superuser)
                url = reverse(name, args=args)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "POST")

    def test_head_returns_405_with_allow_header(self):
        for name, args, _ in self.routes:
            with self.subTest(route=name):
                self.client.force_login(self.superuser)
                url = reverse(name, args=args)
                response = self.client.head(url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "POST")

    # ── Staff (non-superuser) POST → 403 ──────────────────────

    def test_staff_post_returns_403_and_service_not_called(self):
        for name, args, svc_path in self.routes:
            with self.subTest(route=name):
                self.client.force_login(self.staff_user)
                url = reverse(name, args=args)
                with patch(svc_path) as mock_svc:
                    response = self.client.post(url, {})
                    self.assertEqual(response.status_code, 403)
                    mock_svc.assert_not_called()

    # ── CSRF-less POST → 403 ───────────────────────────────────

    def test_csrfless_post_returns_403(self):
        for name, args, svc_path in self.routes:
            with self.subTest(route=name):
                csrf_client = Client(enforce_csrf_checks=True)
                csrf_client.force_login(self.superuser)
                url = reverse(name, args=args)
                with patch(svc_path) as mock_svc:
                    response = csrf_client.post(url, {})
                    self.assertEqual(response.status_code, 403)
                    mock_svc.assert_not_called()

    # ── Missing object → 404 ───────────────────────────────────

    def test_missing_object_returns_404(self):
        for name, _, svc_path in self.routes:
            with self.subTest(route=name):
                self.client.force_login(self.superuser)
                url = reverse(name, args=[self.missing_pk])
                with patch(svc_path) as mock_svc:
                    response = self.client.post(url, {})
                    self.assertEqual(response.status_code, 404)
                    mock_svc.assert_not_called()

    # ── Active superuser POST still works ─────────────────────

    def test_superuser_post_user_sync_returns_redirect(self):
        name, args, svc_path = ("admin:users_user_sync", [self.test_user.pk], "apps.users.admin.UserSyncService")
        self.client.force_login(self.superuser)
        url = reverse(name, args=args)
        with patch(svc_path) as mock_svc:
            mock_instance = mock_svc.return_value
            response = self.client.post(url, {})
            self.assertEqual(response.status_code, 302)
            mock_instance.sync_existing_binding.assert_called_once()

    def test_superuser_post_device_sync_returns_redirect(self):
        name, args, svc_path = (
            "admin:users_syncdevicebinding_sync",
            [self.test_device.pk],
            "apps.users.admin.DeviceSyncService",
        )
        self.client.force_login(self.superuser)
        url = reverse(name, args=args)
        with patch(svc_path) as mock_svc:
            mock_instance = mock_svc.return_value
            response = self.client.post(url, {})
            self.assertEqual(response.status_code, 302)
            mock_instance.sync_existing_binding.assert_called_once()


class StaffPermissionTests(TestCase):
    """Staff with Django model permissions must not get admin access."""

    def setUp(self):
        from django.contrib.auth.models import Permission

        self.superuser = User.objects.create_superuser(
            username="perm_admin", password="pass12345",
        )

        self.staff_with_perm = User.objects.create_user(
            username="perm_staff", password="pass12345",
            is_staff=True, is_superuser=False, is_active=True,
        )
        change_user_perm = Permission.objects.get(
            content_type__app_label="auth", codename="change_user",
        )
        self.staff_with_perm.user_permissions.add(change_user_perm)

        self.test_user = User.objects.create_user(
            username="perm_target", password="pass12345",
        )

    def test_staff_with_permission_cannot_view_user_admin(self):
        self.client.force_login(self.staff_with_perm)
        url = reverse("admin:auth_user_change", args=[self.test_user.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_staff_with_permission_cannot_change_user_admin(self):
        self.client.force_login(self.staff_with_perm)
        url = reverse("admin:auth_user_change", args=[self.test_user.pk])
        response = self.client.post(url, {"username": "hacked"})
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access_user_admin(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:auth_user_change", args=[self.test_user.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class PrivilegeEscalationTests(TestCase):
    """POST with is_superuser, groups or permissions fields must not escalate."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="esc_admin", password="pass12345",
        )
        self.managed_user = User.objects.create_user(
            username="esc_managed", password="pass12345",
        )

    def test_post_with_is_superuser_does_not_escalate(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:auth_user_change", args=[self.managed_user.pk])
        response = self.client.post(url, {
            "username": "esc_managed",
            "email": "esc@test.com",
            "is_superuser": "on",
            "_save": "Save",
        })
        self.managed_user.refresh_from_db()
        self.assertFalse(self.managed_user.is_superuser)


class IsRootFunctionTests(TestCase):
    """Non-superuser with binding/profile role 'root' does not pass is_root()."""

    def setUp(self):
        self.binding_root = User.objects.create_user(
            username="binding_root", password="pass12345",
            is_superuser=False, is_active=True,
        )
        SyncUserBinding.objects.create(user=self.binding_root, sync_role=Role.ROOT)

        self.profile_root = User.objects.create_user(
            username="profile_root", password="pass12345",
            is_superuser=False, is_active=True,
        )
        UserProfile.objects.create(user=self.profile_root, role=Role.ROOT)

        self.true_superuser = User.objects.create_superuser(
            username="true_root", password="pass12345",
        )
        self.inactive_superuser = User.objects.create_superuser(
            username="inactive_root", password="pass12345", is_active=False,
        )

    def test_binding_root_not_is_root(self):
        from apps.common.permissions import is_root
        self.assertFalse(is_root(self.binding_root))

    def test_profile_root_not_is_root(self):
        from apps.common.permissions import is_root
        self.assertFalse(is_root(self.profile_root))

    def test_superuser_is_root(self):
        from apps.common.permissions import is_root
        self.assertTrue(is_root(self.true_superuser))

    def test_inactive_superuser_not_is_root(self):
        from apps.common.permissions import is_root
        self.assertFalse(is_root(self.inactive_superuser))

    def test_anonymous_not_is_root(self):
        from apps.common.permissions import is_root
        anonymous = User()
        self.assertFalse(is_root(anonymous))


class SyncUserBindingAdminReadOnlyTests(TestCase):
    """SyncUserBindingAdmin is diagnostic read-only."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="binding_admin", password="pass12345",
        )
        self.staff_user = User.objects.create_user(
            username="binding_staff", password="pass12345",
            is_staff=True, is_superuser=False, is_active=True,
        )
        self.target_user = User.objects.create_user(
            username="binding_target", password="pass12345",
        )
        self.binding = SyncUserBinding.objects.create(
            user=self.target_user, sync_role=Role.STOREKEEPER,
        )

    def test_staff_cannot_view_changelist(self):
        self.client.force_login(self.staff_user)
        url = reverse("admin:users_syncuserbinding_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_view_changelist(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:users_syncuserbinding_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_has_no_add_permission(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:users_syncuserbinding_add")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_has_no_delete_permission(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:users_syncuserbinding_delete", args=[self.binding.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_change_form_loads_with_readonly_fields(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:users_syncuserbinding_change", args=[self.binding.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.target_user.username)
        self.assertContains(response, Role.STOREKEEPER.label)


class LoginAttemptAdminReadOnlyTests(TestCase):
    """LoginAttemptAdmin read-only with delete-only-for-superuser."""

    def setUp(self):
        from apps.users.models import LoginAttempt

        self.superuser = User.objects.create_superuser(
            username="la_admin", password="pass12345",
        )
        self.staff_user = User.objects.create_user(
            username="la_staff", password="pass12345",
            is_staff=True, is_superuser=False, is_active=True,
        )
        self.attempt = LoginAttempt.objects.create(
            user=self.superuser, action="login",
        )

    def test_staff_cannot_view_changelist(self):
        self.client.force_login(self.staff_user)
        url = reverse("admin:users_loginattempt_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_view_changelist(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:users_loginattempt_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_delete(self):
        self.client.force_login(self.staff_user)
        url = reverse("admin:users_loginattempt_delete", args=[self.attempt.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_delete(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:users_loginattempt_delete", args=[self.attempt.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
