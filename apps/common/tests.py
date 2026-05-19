from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from apps.common.context_processors import _ROLE_LABELS, shell_context, sync_identity_context


class ShellContextProcessorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_shell_context_returns_organization_settings(self):
        request = self.factory.get("/")
        ctx = shell_context(request)
        self.assertEqual(ctx["organization_short_name"], settings.ORGANIZATION_SHORT_NAME)
        self.assertEqual(ctx["organization_full_name"], settings.ORGANIZATION_FULL_NAME)
        self.assertEqual(ctx["organization_logo_static_path"], "img/logo.png")

    def test_shell_context_logo_falls_back_to_default(self):
        request = self.factory.get("/")
        ctx = shell_context(request)
        self.assertEqual(ctx["organization_logo_static_path"], "img/logo.png")


class SyncIdentityContextProcessorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_anonymous_user_has_no_identity(self):
        request = self.factory.get("/")
        request.user = MagicMock(is_authenticated=False)
        ctx = sync_identity_context(request)
        self.assertIsNone(ctx["sync_role"])
        self.assertIsNone(ctx["sync_role_label"])
        self.assertFalse(ctx["has_sync_identity"])

    def test_no_identity_in_session_returns_false(self):
        request = self.factory.get("/")
        request.user = MagicMock(is_authenticated=True)
        request.session = {}
        ctx = sync_identity_context(request)
        self.assertIsNone(ctx["sync_role"])
        self.assertFalse(ctx["has_sync_identity"])

    @patch("apps.common.context_processors.get_sync_identity")
    def test_identity_returned_for_authenticated_user(self, mock_get):
        mock_identity = MagicMock()
        mock_identity.role = "storekeeper"
        mock_get.return_value = mock_identity

        request = self.factory.get("/")
        request.user = MagicMock(is_authenticated=True)
        request.session = {"sync_user_token": "tok"}

        ctx = sync_identity_context(request)
        self.assertEqual(ctx["sync_role"], "storekeeper")
        self.assertEqual(ctx["sync_role_label"], "Кладовщик")
        self.assertTrue(ctx["has_sync_identity"])

    def test_all_role_labels_are_defined(self):
        expected_roles = {"root", "chief_storekeeper", "storekeeper", "observer"}
        self.assertEqual(set(_ROLE_LABELS.keys()), expected_roles)

    def test_unknown_role_uses_capitalized_fallback(self):
        from apps.common.context_processors import _get_role_label
        self.assertEqual(_get_role_label("custom_role"), "Custom_role")
