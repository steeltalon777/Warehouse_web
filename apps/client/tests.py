from unittest.mock import MagicMock, patch

import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.users.models import SyncUserBinding


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        SyncUserBinding.objects.create(
            user=self.user,
            syncserver_user_id="00000000-0000-0000-0000-000000000001",
            sync_user_token="test-token",
            sync_role="storekeeper",
        )

    def _prepare_session(self):
        session = self.client.session
        session["sync_role"] = "storekeeper"
        session["sync_user_token"] = "test-token"
        session["sync_user_id"] = "user-1"
        session["sync_is_root"] = False
        session["sync_available_sites"] = []
        session["sync_default_site_id"] = ""
        session.save()

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("client:dashboard"))
        self.assertRedirects(response, f"/login/?next={reverse('client:dashboard')}")

    def test_dashboard_returns_200_for_authenticated_user(self):
        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_organization_name_in_context(self):
        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertContains(response, settings.ORGANIZATION_SHORT_NAME, html=True)

    def test_dashboard_contains_username(self):
        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertContains(response, "testuser")

    def test_dashboard_contains_role_badge_when_identity_present(self):
        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertContains(response, "role-badge")
        self.assertContains(response, "Кладовщик")

    def test_dashboard_shows_unbound_role_when_no_identity(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("client:dashboard"))
        self.assertContains(response, "роль не привязана")

    def test_dashboard_review_item_count_renders(self):
        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertContains(response, "ТМЦ, требующие проверки")

    def test_dashboard_review_items_graceful_fallback(self):
        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertContains(response, "Данные временно недоступны")

    def test_dashboard_navbar_has_logout_button(self):
        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertContains(response, "Выход")

    def test_dashboard_all_accessible_roles_render_badge(self):
        for idx, (role_key, role_label) in enumerate([
            ("storekeeper", "Кладовщик"),
            ("chief_storekeeper", "Главный кладовщик"),
            ("root", "Root"),
        ]):
            user = User.objects.create_user(
                username=f"testuser_{role_key}", password="testpass"
            )
            SyncUserBinding.objects.create(
                user=user,
                syncserver_user_id=uuid.uuid4(),
                sync_user_token=f"token-{role_key}",
                sync_role=role_key,
            )
            if role_key == "root":
                user.is_superuser = True
                user.save()
            self.client.force_login(user)
            session = self.client.session
            session["sync_role"] = role_key
            session["sync_user_token"] = f"token-{role_key}"
            session["sync_user_id"] = f"user-{role_key}-{idx}"
            session["sync_is_root"] = role_key == "root"
            session["sync_available_sites"] = []
            session["sync_default_site_id"] = ""
            session.save()
            response = self.client.get(reverse("client:dashboard"))
            self.assertEqual(response.status_code, 200, msg=f"Failed for role {role_key}")
            self.assertContains(response, role_label, msg_prefix=f"Role {role_key}")
            self.client.logout()


class DashboardViewIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testsuperuser", password="testpass")
        self.user.is_superuser = True
        self.user.save()

    def _prepare_session(self):
        session = self.client.session
        session["sync_role"] = "root"
        session["sync_user_token"] = "test-token"
        session["sync_user_id"] = "user-1"
        session["sync_is_root"] = True
        session["sync_available_sites"] = []
        session["sync_default_site_id"] = ""
        session.save()

    @patch("apps.client.views.TemporaryItemsAPI")
    def test_dashboard_renders_temp_item_count_from_api(self, mock_temp_api):
        mock_instance = MagicMock()
        mock_instance.list_temporary_items.return_value = []
        mock_instance.list_temporary_items_page.return_value = {
            "items": [], "total_count": 5, "page": 1, "page_size": 1
        }
        mock_temp_api.return_value = mock_instance

        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertContains(response, "5")

    @patch("apps.client.views.TemporaryItemsAPI")
    def test_dashboard_renders_zero_count(self, mock_temp_api):
        mock_instance = MagicMock()
        mock_instance.list_temporary_items.return_value = []
        mock_instance.list_temporary_items_page.return_value = {
            "items": [], "total_count": 0, "page": 1, "page_size": 1
        }
        mock_temp_api.return_value = mock_instance

        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertContains(response, "0")

    @patch("apps.client.views.ReviewItemsAPI")
    def test_dashboard_handles_api_error_gracefully(self, mock_review_api):
        mock_instance = MagicMock()
        mock_instance.list_review_items_page.side_effect = Exception("API unavailable")
        mock_review_api.return_value = mock_instance

        self.client.force_login(self.user)
        self._prepare_session()
        response = self.client.get(reverse("client:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нет ТМЦ, требующих проверки")

    def test_dashboard_observer_gets_forbidden(self):
        user = User.objects.create_user(username="observer_user", password="testpass")
        SyncUserBinding.objects.create(
            user=user,
            syncserver_user_id=uuid.uuid4(),
            sync_user_token="token-observer",
            sync_role="observer",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("client:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_no_tokens_in_html(self):
        self.client.force_login(self.user)
        self._prepare_session()
        session = self.client.session
        session["sync_user_token"] = "test-token-12345"
        session.save()
        response = self.client.get(reverse("client:dashboard"))
        self.assertNotContains(response, "test-token-12345")
