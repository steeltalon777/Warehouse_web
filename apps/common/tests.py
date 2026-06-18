from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from structlog.testing import capture_logs

from apps.common.context_processors import _ROLE_LABELS, shell_context, sync_identity_context
from apps.common.middleware import RequestTracingMiddleware


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


class RequestTracingMiddlewareAccessLogTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @staticmethod
    def _ok_view(request):
        return HttpResponse(status=200)

    @staticmethod
    def _not_found_view(request):
        return HttpResponse(status=404)

    @staticmethod
    def _broken_view(request):
        raise ValueError("test error")

    def test_healthz_logs_info(self):
        request = self.factory.get("/healthz/")
        middleware = RequestTracingMiddleware(self._ok_view)
        with capture_logs() as cap_logs:
            middleware(request)
            events = [e for e in cap_logs if e.get("event") == "http_request"]
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event["method"], "GET")
            self.assertEqual(event["path"], "/healthz/")
            self.assertEqual(event["status_code"], 200)
            self.assertIn("duration_ms", event)
            self.assertIn("request_id", event)
            self.assertEqual(event["log_level"], "info")

    def test_not_found_logs_warning(self):
        request = self.factory.get("/nonexistent/")
        middleware = RequestTracingMiddleware(self._not_found_view)
        with capture_logs() as cap_logs:
            middleware(request)
            events = [e for e in cap_logs if e.get("event") == "http_request"]
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event["method"], "GET")
            self.assertEqual(event["status_code"], 404)
            self.assertEqual(event["log_level"], "warning")

    def test_x_request_id_set_on_response(self):
        request = self.factory.get("/test/")
        middleware = RequestTracingMiddleware(self._ok_view)
        with capture_logs():
            response = middleware(request)
        self.assertIn("X-Request-Id", response)
        self.assertTrue(response["X-Request-Id"])

    def test_access_log_not_contains_secrets(self):
        request = self.factory.get("/secure/", HTTP_AUTHORIZATION="Bearer secret-token-42")
        middleware = RequestTracingMiddleware(self._ok_view)
        with capture_logs() as cap_logs:
            middleware(request)
            events = [e for e in cap_logs if e.get("event") == "http_request"]
            self.assertEqual(len(events), 1)
            event_str = str(events[0])
            self.assertNotIn("secret-token-42", event_str)
            self.assertNotIn("Authorization", event_str)
            expected_keys = {"event", "method", "path", "status_code", "duration_ms", "request_id", "log_level"}
            self.assertTrue(expected_keys.issuperset(events[0].keys()))

    def test_middleware_exception_logs_error(self):
        request = self.factory.get("/broken/")
        middleware = RequestTracingMiddleware(self._broken_view)
        with capture_logs() as cap_logs:
            with self.assertRaises(ValueError):
                middleware(request)
            events = [e for e in cap_logs if e.get("event") == "http_request"]
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event["status_code"], 500)
            self.assertEqual(event["log_level"], "error")
            self.assertIn("duration_ms", event)
            self.assertIn("request_id", event)
