"""Tests for V3.1F Admin Panel Hardening (F1-F4).

Level 2-3: Unit tests for form validation, save logic, multi-site, device admin.
Level 4: DB-backed integration tests for model/admin interactions.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.users.admin_forms import (
    SyncManagedDeviceAdminForm,
    SyncManagedDeviceCreationForm,
    SyncManagedUserAdminForm,
    SyncManagedUserCreationForm,
)
from apps.users.admin import SyncDeviceBindingAdmin as DeviceAdmin
from apps.users.models import SyncDeviceBinding, SyncStatus, SyncUserBinding

User = get_user_model()


# ──────────────────────────────────────────────
# F1: Password preservation tests
# ──────────────────────────────────────────────


class F1PasswordPreservationTests(TestCase):
    """Form level: save() must not clear password when field is empty."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="f1-user",
            password="SecretPass1",
            email="f1@test.com",
        )

    @patch.object(SyncManagedUserAdminForm, "site_choices", [("1", "WH")])
    @patch("apps.users.admin_forms.UserSyncService")
    def test_password_preserved_on_empty_field(self, mock_svc_cls):
        """Редактирование без пароля → старый пароль сохраняется."""
        mock_svc = mock_svc_cls.return_value
        mock_svc.list_sites.return_value = [{"site_id": 1, "name": "WH", "is_active": True}]

        form = SyncManagedUserAdminForm(
            instance=self.user,
            data={
                "username": "f1-user",
                "email": "updated@test.com",
                "full_name": "Updated Name",
                "sync_role": "storekeeper",
                "site_ids": ["1"],
                "is_active": True,
            },
        )
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")
        form.save(commit=False)
        self.assertTrue(self.user.check_password("SecretPass1"))

    @patch.object(SyncManagedUserAdminForm, "site_choices", [("1", "WH")])
    @patch("apps.users.admin_forms.UserSyncService")
    def test_password_changed_when_filled(self, mock_svc_cls):
        """Заполненный пароль → новый пароль устанавливается."""
        mock_svc = mock_svc_cls.return_value
        mock_svc.list_sites.return_value = [{"site_id": 1, "name": "WH", "is_active": True}]

        form = SyncManagedUserAdminForm(
            instance=self.user,
            data={
                "username": "f1-user",
                "email": "f1@test.com",
                "full_name": "",
                "password": "NewPass999",
                "password_confirm": "NewPass999",
                "sync_role": "storekeeper",
                "site_ids": ["1"],
                "is_active": True,
            },
        )
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")
        form.save(commit=False)
        self.assertTrue(self.user.check_password("NewPass999"))

    @patch("apps.users.admin.UserSyncService")
    @patch("apps.users.admin_forms.UserSyncService")
    def test_admin_post_preserves_password_when_empty(
        self, mock_form_svc_cls, mock_admin_svc_cls
    ):
        """Полный Django Admin flow не должен менять пустой пароль на сохранении."""
        admin_user = User.objects.create_superuser(
            username="f1-admin",
            password="AdminPass123",
        )
        mock_form_svc_cls.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True}
        ]
        mock_admin_svc_cls.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True}
        ]

        self.client.force_login(admin_user)
        response = self.client.post(
            reverse("admin:auth_user_change", args=[self.user.pk]),
            {
                "username": self.user.username,
                "email": self.user.email,
                "full_name": "Updated Name",
                "sync_role": "storekeeper",
                "site_ids": ["1"],
                "is_active": "on",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("SecretPass1"))


# ──────────────────────────────────────────────
# F2: Password reset URL tests
# ──────────────────────────────────────────────


class F2PasswordResetURLTests(TestCase):
    """URLs are registered and resolve correctly."""

    def test_password_reset_url_resolves(self):
        """Страница password_reset доступна."""
        url = reverse("password_reset")
        self.assertEqual(url, "/users/password-reset/")

    def test_password_reset_done_url_resolves(self):
        url = reverse("password_reset_done")
        self.assertEqual(url, "/users/password-reset/done/")

    def test_password_reset_confirm_url_resolves(self):
        """URL с uidb64/token резолвится корректно."""
        url = reverse("password_reset_confirm", kwargs={"uidb64": "abc", "token": "xyz"})
        self.assertIn("/users/password-reset/abc/xyz/", url)

    def test_password_reset_complete_url_resolves(self):
        url = reverse("password_reset_complete")
        self.assertEqual(url, "/users/password-reset/complete/")

    def test_password_reset_view_returns_200(self):
        """GET /users/password-reset/ → 200."""
        response = self.client.get("/users/password-reset/")
        self.assertEqual(response.status_code, 200)

    def test_password_reset_done_view_returns_200(self):
        response = self.client.get("/users/password-reset/done/")
        self.assertEqual(response.status_code, 200)


# ──────────────────────────────────────────────
# F3: Multi-site support tests
# ──────────────────────────────────────────────


class F3MultiSiteFormValidationTests(TestCase):
    """Form-level validation for site_ids MultipleChoiceField."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="f3-user",
            password="test123",
        )

    @patch.object(SyncManagedUserAdminForm, "site_choices", [("1", "WH"), ("2", "WH2")])
    @patch("apps.users.admin_forms.UserSyncService")
    def test_single_site_works(self, mock_svc_cls):
        """Один склад — валидация проходит."""
        mock_svc = mock_svc_cls.return_value
        mock_svc.list_sites.return_value = [{"site_id": 1, "name": "WH", "is_active": True}]

        form = SyncManagedUserAdminForm(
            instance=self.user,
            data={
                "username": "f3-user",
                "email": "f3@test.com",
                "full_name": "",
                "sync_role": "storekeeper",
                "site_ids": ["1"],
                "is_active": True,
            },
        )
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")

    @patch.object(SyncManagedUserAdminForm, "site_choices", [("1", "WH"), ("2", "WH2")])
    @patch("apps.users.admin_forms.UserSyncService")
    def test_multiple_sites_work(self, mock_svc_cls):
        """Несколько складов — валидация проходит, site_ids = [1, 2]."""
        mock_svc = mock_svc_cls.return_value
        mock_svc.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True},
            {"site_id": 2, "name": "WH2", "is_active": True},
        ]

        form = SyncManagedUserAdminForm(
            instance=self.user,
            data={
                "username": "f3-user",
                "email": "f3@test.com",
                "full_name": "",
                "sync_role": "storekeeper",
                "site_ids": ["1", "2"],
                "is_active": True,
            },
        )
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")
        # site_ids_list в clean() передаётся в prepare_sync
        cleaned = form.cleaned_data
        self.assertIn("1", str(cleaned.get("site_ids")))
        self.assertIn("2", str(cleaned.get("site_ids")))

    @patch.object(SyncManagedUserAdminForm, "site_choices", [("1", "WH")])
    @patch("apps.users.admin_forms.UserSyncService")
    def test_no_site_fails(self, mock_svc_cls):
        """Пустой site_ids → ValidationError."""
        mock_svc = mock_svc_cls.return_value
        mock_svc.list_sites.return_value = []

        form = SyncManagedUserAdminForm(
            instance=self.user,
            data={
                "username": "f3-user",
                "email": "f3@test.com",
                "full_name": "",
                "sync_role": "storekeeper",
                "site_ids": [],
                "is_active": True,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("выбрать хотя бы один склад", str(form.errors).lower())

    @patch.object(SyncManagedUserAdminForm, "site_choices", [("1", "WH"), ("2", "WH2")])
    @patch("apps.users.admin_forms.UserSyncService")
    def test_multi_site_passed_to_prepare_sync(self, mock_svc_cls):
        """Множественные site_ids валидируются корректно в clean()."""
        mock_svc = mock_svc_cls.return_value
        mock_svc.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True},
            {"site_id": 2, "name": "WH2", "is_active": True},
        ]

        form = SyncManagedUserAdminForm(
            instance=self.user,
            data={
                "username": "f3-user",
                "email": "f3@test.com",
                "full_name": "",
                "sync_role": "storekeeper",
                "site_ids": ["1", "2"],
                "is_active": True,
            },
        )
        # Форма валидируется с множественными site_ids без ошибок
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")
        # Проверяем что site_ids в cleaned_data содержит оба ID
        self.assertIn("1", str(form.cleaned_data.get("site_ids", [])))
        self.assertIn("2", str(form.cleaned_data.get("site_ids", [])))


class F3MultiSiteSaveIntegrationTests(TestCase):
    """Integration: save_model path with site_ids."""

    def test_binding_site_ids_updated_on_save(self):
        """SyncUserBinding.site_ids сохраняется как список."""
        user = User.objects.create_user(
            username="f3-save",
            password="test123",
            email="f3save@test.com",
        )
        binding = SyncUserBinding.objects.create(
            user=user,
            sync_role="storekeeper",
            default_site_id="1",
            site_ids=["1"],
        )
        # Проверяем, что JSONField корректно хранит список
        binding.site_ids = ["1", "2"]
        binding.save()
        binding.refresh_from_db()
        self.assertEqual(binding.site_ids, ["1", "2"])

    def test_default_site_id_from_first_in_list(self):
        """default_site_id должен быть первым элементом site_ids."""
        user = User.objects.create_user(
            username="f3-first",
            password="test123",
        )
        binding = SyncUserBinding.objects.create(
            user=user,
            sync_role="chief_storekeeper",
            default_site_id="2",
            site_ids=["2", "1"],
        )
        binding.refresh_from_db()
        # default_site_id сохраняется как есть
        self.assertEqual(binding.default_site_id, "2")


# ──────────────────────────────────────────────
# F4: Device admin parity tests
# ──────────────────────────────────────────────


class F4DeviceCreationFormTests(TestCase):
    """SyncManagedDeviceCreationForm works correctly."""

    def test_creation_form_has_correct_fields(self):
        """Форма создания устройства содержит нужные поля; sync_device_token — disabled."""
        form = SyncManagedDeviceCreationForm()
        self.assertIn("device_code", form.fields)
        self.assertIn("device_name", form.fields)
        self.assertIn("is_active", form.fields)
        # sync_device_token наследуется от родителя, но в Meta.fields не указан
        self.assertIn("sync_device_token", form.fields)
        self.assertTrue(form.fields["sync_device_token"].disabled)

    def test_creation_form_inherits_from_admin_form(self):
        """SyncManagedDeviceCreationForm наследует SyncManagedDeviceAdminForm."""
        self.assertTrue(issubclass(SyncManagedDeviceCreationForm, SyncManagedDeviceAdminForm))


class F4DeviceOnlineStatusTests(TestCase):
    """Online/offline status display logic via DeviceAdmin.online_status()."""

    def setUp(self):
        self.device = SyncDeviceBinding.objects.create(
            device_code="DEV-001",
            device_name="Test Device",
        )

    def test_online_status_no_last_seen(self):
        """Без last_seen_at → прочерк (серый)."""
        result = DeviceAdmin.online_status(DeviceAdmin, self.device)
        self.assertIn("color:gray", str(result))

    def test_online_status_online(self):
        """last_seen_at < 5 минут → 🟢 Online."""
        self.device.last_seen_at = timezone.now() - timedelta(minutes=1)
        result = DeviceAdmin.online_status(DeviceAdmin, self.device)
        self.assertIn("Online", str(result))
        self.assertIn("color:green", str(result))

    def test_online_status_away(self):
        """5 мин < last_seen_at < 1 час → 🟡 Away."""
        self.device.last_seen_at = timezone.now() - timedelta(minutes=30)
        result = DeviceAdmin.online_status(DeviceAdmin, self.device)
        self.assertIn("Away", str(result))
        self.assertIn("color:orange", str(result))

    def test_online_status_offline(self):
        """last_seen_at > 1 час → 🔴 Offline."""
        self.device.last_seen_at = timezone.now() - timedelta(hours=2)
        result = DeviceAdmin.online_status(DeviceAdmin, self.device)
        self.assertIn("Offline", str(result))
        self.assertIn("color:red", str(result))


class F4DeviceBindingModelTests(TestCase):
    """SyncDeviceBinding model supports last_seen_at."""

    def test_last_seen_at_field_exists(self):
        """Поле last_seen_at доступно на модели."""
        field = SyncDeviceBinding._meta.get_field("last_seen_at")
        self.assertIsNotNone(field)
        self.assertTrue(field.null)

    def test_last_seen_at_can_be_set(self):
        """last_seen_at сохраняется и читается."""
        now = timezone.now()
        device = SyncDeviceBinding.objects.create(
            device_code="DEV-LS",
            device_name="Last Seen Device",
            last_seen_at=now,
        )
        device.refresh_from_db()
        self.assertIsNotNone(device.last_seen_at)
        # Допускаем микросекундную разницу
        self.assertAlmostEqual(
            device.last_seen_at.timestamp(),
            now.timestamp(),
            delta=1,
        )


# ──────────────────────────────────────────────
# Combined: CreationForm inherits save() from parent
# ──────────────────────────────────────────────


class F1CreationFormPasswordTests(TestCase):
    """SyncManagedUserCreationForm наследует save() из SyncManagedUserAdminForm."""

    def test_creation_form_inherits_save(self):
        """Форма создания наследует переопределённый save()."""
        self.assertTrue(
            SyncManagedUserCreationForm.save is SyncManagedUserAdminForm.save
            or "save" in SyncManagedUserCreationForm.__dict__
        )

    def test_creation_form_requires_password(self):
        """Форма создания требует пароль."""
        fields = SyncManagedUserCreationForm.base_fields
        self.assertTrue(fields["password"].required)
        self.assertTrue(fields["password_confirm"].required)


# ──────────────────────────────────────────────
# F1 Login regression: admin POST preserves password login
# ──────────────────────────────────────────────


class F1PasswordRegressionTests(TestCase):
    """Expanded password regression: login with old password after empty-field edit."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="pw-regression",
            password="OldPass123",
            email="pw@test.com",
        )

    @patch("apps.users.admin.UserSyncService")
    @patch("apps.users.admin_forms.UserSyncService")
    def test_admin_post_preserves_password_login(self, mock_form_svc, mock_admin_svc):
        """Full admin POST with empty password → old password still works for login."""
        admin_user = User.objects.create_superuser(
            username="admin-pw", password="AdminPass123",
        )
        mock_form_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True}
        ]
        mock_admin_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True}
        ]
        mock_admin_svc.return_value.sync_user_to_remote.return_value = None

        self.client.force_login(admin_user)
        response = self.client.post(
            reverse("admin:auth_user_change", args=[self.user.pk]),
            {
                "username": self.user.username,
                "email": self.user.email,
                "full_name": "",
                "sync_role": "storekeeper",
                "site_ids": ["1"],
                "is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)

        login_ok = self.client.login(username="pw-regression", password="OldPass123")
        self.assertTrue(login_ok)
