"""Tests for UserProfileForm and profile_view (Level 3 + Level 4)."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from apps.users.admin_forms import SyncManagedUserAdminForm
from apps.users.forms import UserProfileForm
from apps.users.models import SyncUserBinding


User = get_user_model()


# ──────────────────────────────────────────────
# Level 3: Unit tests for UserProfileForm
# ──────────────────────────────────────────────


class UserProfileFormTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testuser",
            password="OldPass123",
            first_name="Old Name",
            email="old@test.com",
        )

    def test_current_password_required(self) -> None:
        """Пустой current_password → validation error."""
        form = UserProfileForm(self.user, data={})
        self.assertFalse(form.is_valid())
        self.assertIn("current_password", form.errors)

    def test_wrong_current_password(self) -> None:
        """Неверный текущий пароль → validation error."""
        form = UserProfileForm(
            self.user,
            data={
                "current_password": "WrongPass",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("current_password", form.errors)

    def test_password_change_mismatch(self) -> None:
        """new_password ≠ confirm → validation error."""
        form = UserProfileForm(
            self.user,
            data={
                "current_password": "OldPass123",
                "new_password": "NewPass456",
                "new_password_confirm": "Different789",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_password_change_success(self) -> None:
        """Правильные данные, меняем пароль."""
        form = UserProfileForm(
            self.user,
            data={
                "current_password": "OldPass123",
                "new_password": "NewPass456",
                "new_password_confirm": "NewPass456",
            },
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["new_password"], "NewPass456")

    def test_password_unchanged_when_empty(self) -> None:
        """Пустые поля пароля → пароль не меняется (пустая строка)."""
        form = UserProfileForm(
            self.user,
            data={
                "current_password": "OldPass123",
                "full_name": "New Name",
            },
        )
        self.assertTrue(form.is_valid())
        # Django CharField(required=False) returns "" for missing values
        self.assertEqual(form.cleaned_data.get("new_password"), "")

    def test_full_name_update(self) -> None:
        """Меняем ФИО."""
        form = UserProfileForm(
            self.user,
            data={
                "current_password": "OldPass123",
                "full_name": "Новое ФИО",
            },
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["full_name"], "Новое ФИО")

    def test_email_update(self) -> None:
        """Меняем email."""
        form = UserProfileForm(
            self.user,
            data={
                "current_password": "OldPass123",
                "email": "new@test.com",
            },
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["email"], "new@test.com")

    def test_email_invalid(self) -> None:
        """Невалидный email → validation error."""
        form = UserProfileForm(
            self.user,
            data={
                "current_password": "OldPass123",
                "email": "not-an-email",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


# ──────────────────────────────────────────────
# Level 4: Integration tests for profile_view (DB-backed)
# ──────────────────────────────────────────────


class ProfileViewTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="profile-user",
            password="ProfilePass1",
            first_name="Initial",
            email="initial@test.com",
        )

    def test_profile_view_get_requires_login(self) -> None:
        """Без аутентификации → redirect на login."""
        response = self.client.get(reverse("users:profile"))
        # LOGIN_URL is set to /login/ in base settings
        login_url = settings.LOGIN_URL
        self.assertRedirects(
            response,
            f"{login_url}?next={reverse('users:profile')}",
        )

    def test_profile_view_get_authenticated(self) -> None:
        """GET /users/profile/ с аутентификацией → 200 + форма."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("users:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Профиль")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_profile_view_post_success(self) -> None:
        """POST с правильными данными → success message."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("users:profile"),
            {
                "current_password": "ProfilePass1",
                "new_password": "NewPass789",
                "new_password_confirm": "NewPass789",
                "full_name": "Updated Name",
                "email": "updated@test.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Данные сохранены")

        # Проверяем, что пароль и данные обновились
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass789"))
        self.assertEqual(self.user.first_name, "Updated Name")
        self.assertEqual(self.user.email, "updated@test.com")

    def test_profile_view_post_wrong_password(self) -> None:
        """POST с неверным текущим паролем → ошибка."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("users:profile"),
            {
                "current_password": "WrongPassword",
                "full_name": "Should Not Change",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Данные сохранены")
        self.assertContains(response, "Неверный текущий пароль")

    def test_profile_view_post_partial_update(self) -> None:
        """Только ФИО/email без смены пароля."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("users:profile"),
            {
                "current_password": "ProfilePass1",
                "full_name": "Just Name",
                "email": "justname@test.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Данные сохранены")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ProfilePass1"))  # пароль не изменился
        self.assertEqual(self.user.first_name, "Just Name")
        self.assertEqual(self.user.email, "justname@test.com")

    @patch("apps.users.views.UserSyncService.sync_existing_binding")
    def test_profile_view_sync_called(self, mock_sync) -> None:
        """SyncServer синк вызывается при наличии binding."""
        SyncUserBinding.objects.create(
            user=self.user,
            syncserver_user_id="00000000-0000-0000-0000-000000000001",
            sync_user_token="test-token",
            sync_role="storekeeper",
        )
        self.client.force_login(self.user)
        self.client.post(
            reverse("users:profile"),
            {
                "current_password": "ProfilePass1",
                "full_name": "Sync Test",
            },
        )
        mock_sync.assert_called_once()

    @patch("apps.users.views.UserSyncService.sync_existing_binding")
    def test_profile_view_sync_skipped_without_binding(self, mock_sync) -> None:
        """Без binding синк не вызывается."""
        self.client.force_login(self.user)
        self.client.post(
            reverse("users:profile"),
            {
                "current_password": "ProfilePass1",
                "full_name": "No Sync",
            },
        )
        mock_sync.assert_not_called()


# ──────────────────────────────────────────────
# Level 3: Admin form clean_password tests
# ──────────────────────────────────────────────


class SyncManagedUserAdminFormPasswordSaveTest(TestCase):
    """Tests for save() in SyncManagedUserAdminForm.

    The method intercepts save() to prevent UserChangeForm
    from calling set_password("") on empty password fields.
    """

    @patch.object(SyncManagedUserAdminForm, "site_choices", [("1", "WH")])
    @patch("apps.users.admin_forms.SyncUserBinding.objects.get_or_create")
    @patch("apps.users.admin_forms.UserSyncService.prepare_sync")
    @patch("apps.users.admin_forms.UserSyncService")
    def test_save_does_not_clear_password_when_empty(
        self, mock_service_cls, mock_prepare, mock_binding
    ) -> None:
        """save() не вызывает set_password('') при пустом поле пароля."""
        user = User.objects.create_user(username="cp-empty", password="secret123")
        mock_service_cls.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True}
        ]
        mock_binding.return_value = (None, False)
        form = SyncManagedUserAdminForm(
            instance=user,
            data={
                "username": "cp-empty",
                "email": "cp@test.com",
                "full_name": "",
                "sync_role": "storekeeper",
                "site_ids": ["1"],
                "is_active": True,
            },
        )
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")
        form.save(commit=False)
        self.assertTrue(user.check_password("secret123"))

    @patch.object(SyncManagedUserAdminForm, "site_choices", [("1", "WH")])
    @patch("apps.users.admin_forms.UserSyncService.prepare_sync")
    @patch("apps.users.admin_forms.UserSyncService")
    def test_save_sets_password_when_provided(
        self, mock_service_cls, mock_prepare
    ) -> None:
        """save() вызывает set_password при заполненном поле пароля."""
        user = User.objects.create_user(username="cp-set", password="oldpass")
        mock_service_cls.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True}
        ]
        form = SyncManagedUserAdminForm(
            instance=user,
            data={
                "username": "cp-set",
                "email": "cp@test.com",
                "full_name": "",
                "password": "newpass123",
                "password_confirm": "newpass123",
                "sync_role": "storekeeper",
                "site_ids": ["1"],
                "is_active": True,
            },
        )
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")
        form.save(commit=False)
        self.assertTrue(user.check_password("newpass123"))
