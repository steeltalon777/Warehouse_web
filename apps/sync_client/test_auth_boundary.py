"""Auth boundary tests for TZ-1.

Covers:
- Token resolver behavior
- SyncServerClient root and non-root auth boundary
- NomenclatureSPAView login requirement
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import SyncAuthError
from apps.sync_client.token_resolver import (
    ResolvedSyncIdentity,
    SyncIdentityNotBoundError,
    resolve_sync_identity,
)


class TokenResolverTests(SimpleTestCase):
    """Tests for the canonical token resolver."""

    def _make_request(self, user=None, session_data=None):
        factory = RequestFactory()
        request = factory.get("/")
        if user is not None:
            request.user = user
        if session_data:
            request.session = session_data
        return request

    def _make_user(self, is_superuser=False, is_authenticated=True, username="testuser"):
        user = Mock()
        user.is_authenticated = is_authenticated
        user.is_superuser = is_superuser
        user.username = username
        user.id = 1
        return user

    def test_anonymous_raises_not_bound(self):
        request = self._make_request(user=None)
        with self.assertRaises(SyncIdentityNotBoundError):
            resolve_sync_identity(request=request)

    def test_non_superuser_no_binding_no_session_raises(self):
        user = self._make_user()
        user.sync_binding = Mock()
        user.sync_binding.sync_user_token = ""
        request = self._make_request(user=user)
        with self.assertRaises(SyncIdentityNotBoundError):
            resolve_sync_identity(request=request)

    def test_non_superuser_with_binding_uses_binding_token(self):
        user = self._make_user()
        binding = Mock()
        binding.sync_user_token = "binding-token-123"
        binding.default_site_id = "site-1"
        user.sync_binding = binding
        request = self._make_request(user=user)

        result = resolve_sync_identity(request=request)

        self.assertEqual(result.user_token, "binding-token-123")
        self.assertEqual(result.source, "binding")
        self.assertFalse(result.is_root)

    def test_non_superuser_session_token_fallback(self):
        user = self._make_user()
        user.sync_binding = Mock()
        user.sync_binding.sync_user_token = ""
        request = self._make_request(
            user=user,
            session_data={"sync_user_token": "session-token-456"},
        )

        result = resolve_sync_identity(request=request)

        self.assertEqual(result.user_token, "session-token-456")
        self.assertEqual(result.source, "session")
        self.assertFalse(result.is_root)

    @override_settings(SYNC_ROOT_USER_TOKEN="root-secret")
    def test_superuser_uses_root_token_from_env(self):
        user = self._make_user(is_superuser=True)
        user.sync_binding = Mock()
        user.sync_binding.sync_user_token = ""
        request = self._make_request(user=user)

        result = resolve_sync_identity(request=request)

        self.assertEqual(result.user_token, "root-secret")
        self.assertEqual(result.source, "root_superuser")
        self.assertTrue(result.is_root)

    @override_settings(SYNC_ROOT_USER_TOKEN="root-secret")
    def test_superuser_uses_root_token_not_binding(self):
        user = self._make_user(is_superuser=True)
        binding = Mock()
        binding.sync_user_token = "super-binding-token"
        binding.default_site_id = "site-2"
        user.sync_binding = binding
        request = self._make_request(user=user)

        result = resolve_sync_identity(request=request)

        self.assertEqual(result.user_token, "root-secret")
        self.assertEqual(result.source, "root_superuser")
        self.assertTrue(result.is_root)

    @override_settings(SYNC_ROOT_USER_TOKEN="root-secret")
    def test_force_root_uses_root_token(self):
        request = self._make_request(user=None)

        result = resolve_sync_identity(request=request, force_root=True)

        self.assertEqual(result.user_token, "root-secret")
        self.assertEqual(result.source, "root_explicit")
        self.assertTrue(result.is_root)

    @override_settings(SYNC_ROOT_USER_TOKEN="")
    def test_force_root_without_config_raises(self):
        request = self._make_request(user=None)
        with self.assertRaises(RuntimeError):
            resolve_sync_identity(request=request, force_root=True)

    def test_binding_takes_priority_over_session(self):
        user = self._make_user()
        binding = Mock()
        binding.sync_user_token = "binding-wins"
        binding.default_site_id = None
        user.sync_binding = binding
        request = self._make_request(
            user=user,
            session_data={"sync_user_token": "session-loses"},
        )

        result = resolve_sync_identity(request=request)

        self.assertEqual(result.user_token, "binding-wins")
        self.assertEqual(result.source, "binding")


class SyncServerClientAuthTests(SimpleTestCase):
    """Tests for SyncServerClient auth boundary enforcement."""

    @override_settings(
        SYNC_SERVER_URL="http://syncserver:8000/api/v1",
        SYNC_DEVICE_TOKEN="",
        SYNC_ROOT_USER_TOKEN="root-token",
    )
    def test_non_superuser_no_binding_does_not_fallback_to_root(self):
        user = Mock()
        user.is_authenticated = True
        user.is_superuser = False
        user.username = "regular_user"
        user.id = 42
        user.sync_binding = Mock()
        user.sync_binding.sync_user_token = ""

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        client = SyncServerClient(request=request)

        with self.assertRaises(SyncIdentityNotBoundError):
            client.build_headers()

    @override_settings(
        SYNC_SERVER_URL="http://syncserver:8000/api/v1",
        SYNC_DEVICE_TOKEN="",
        SYNC_ROOT_USER_TOKEN="root-token",
    )
    def test_non_superuser_with_binding_uses_binding_token(self):
        user = Mock()
        user.is_authenticated = True
        user.is_superuser = False
        user.username = "bound_user"
        user.id = 43
        binding = Mock()
        binding.sync_user_token = "user-token-abc"
        binding.default_site_id = "site-1"
        user.sync_binding = binding

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        client = SyncServerClient(request=request)
        headers = client.build_headers()

        self.assertEqual(headers["X-User-Token"], "user-token-abc")
        self.assertNotIn("X-Device-Token", headers)

    @override_settings(
        SYNC_SERVER_URL="http://syncserver:8000/api/v1",
        SYNC_DEVICE_TOKEN="device-audit-token",
        SYNC_ROOT_USER_TOKEN="root-token",
    )
    def test_device_token_included_when_configured(self):
        user = Mock()
        user.is_authenticated = True
        user.is_superuser = False
        user.username = "bound_user"
        user.id = 44
        binding = Mock()
        binding.sync_user_token = "user-token-xyz"
        binding.default_site_id = None
        user.sync_binding = binding

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        client = SyncServerClient(request=request)
        headers = client.build_headers()

        self.assertEqual(headers["X-Device-Token"], "device-audit-token")

    @override_settings(
        SYNC_SERVER_URL="http://syncserver:8000/api/v1",
        SYNC_DEVICE_TOKEN="",
        SYNC_ROOT_USER_TOKEN="root-token",
    )
    def test_force_root_uses_root_token(self):
        factory = RequestFactory()
        request = factory.get("/")

        client = SyncServerClient(request=request, force_root=True)
        headers = client.build_headers()

        self.assertEqual(headers["X-User-Token"], "root-token")

    @override_settings(
        SYNC_SERVER_URL="http://syncserver:8000/api/v1",
        SYNC_DEVICE_TOKEN="",
        SYNC_ROOT_USER_TOKEN="root-token",
    )
    def test_superuser_normal_flow_uses_root_token(self):
        user = Mock()
        user.is_authenticated = True
        user.is_superuser = True
        user.username = "admin_user"
        user.id = 1
        user.sync_binding = Mock()
        user.sync_binding.sync_user_token = ""

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        client = SyncServerClient(request=request)
        headers = client.build_headers()

        self.assertEqual(headers["X-User-Token"], "root-token")

    @override_settings(
        SYNC_SERVER_URL="http://syncserver:8000/api/v1",
        SYNC_DEVICE_TOKEN="",
        SYNC_ROOT_USER_TOKEN="",
    )
    def test_init_does_not_require_device_token(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = Mock()
        request.user.is_authenticated = False

        client = SyncServerClient(request=request, force_root=False)
        self.assertEqual(client.device_token, "")


class NomenclatureSPAViewAuthTests(TestCase):
    """Tests that NomenclatureSPAView requires authentication."""

    def test_anonymous_redirected_to_login(self):
        response = self.client.get("/nomenclature/")
        self.assertIn(response.status_code, (301, 302))
        self.assertTrue(
            response["Location"].startswith("/login/")
            or response["Location"].startswith("/users/login/"),
            f"Expected redirect to login, got {response['Location']}",
        )

    def test_authenticated_user_gets_spa(self):
        User.objects.create_user(username="spa_user", password="testpass123")
        self.client.login(username="spa_user", password="testpass123")

        response = self.client.get("/nomenclature/")
        self.assertNotIn(response.status_code, (301, 302))
