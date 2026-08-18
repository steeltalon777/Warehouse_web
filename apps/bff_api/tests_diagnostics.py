"""Tests for BFF /bff/api/v1/diagnostics/ui-events/batch endpoint.

TZ-DIAGNOSTICS_STAGE3 WP-1.
"""
from __future__ import annotations

import json
from unittest import mock
from uuid import uuid4

from django.test import TestCase, RequestFactory, override_settings


def _valid_event(event_type: str = "form_opened"):
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "occurred_at": "2026-07-15T10:00:00+00:00",
        "session_id": str(uuid4()),
        "tab_id": str(uuid4()),
        "frontend_version": "e2e",
        "route": "/operations",
        "operation_type": "RECEIVE",
        "severity": "info",
    }


def _valid_batch(event_type: str = "form_opened"):
    return {
        "events": [_valid_event(event_type)],
        "sent_at": "2026-07-15T10:00:00+00:00",
        "sequence": 1,
    }


class DiagnosticsBatchEndpointTests(TestCase):
    def setUp(self):
        from apps.bff_api.diagnostics_views import diagnostics_batch_view
        self.view = diagnostics_batch_view
        self.factory = RequestFactory()

    def _post(self, payload, content_length=None, headers=None):
        body = json.dumps(payload).encode("utf-8")
        kwargs = {"data": body, "content_type": "application/json"}
        if content_length is not None:
            kwargs["CONTENT_LENGTH"] = str(content_length)
        req = self.factory.post("/bff/api/v1/diagnostics/ui-events/batch", **kwargs)
        if headers:
            for k, v in headers.items():
                req.META[f"HTTP_{k.upper().replace('-', '_')}"] = v
        return self.view(req)

    @mock.patch("apps.bff_api.diagnostics_views.SyncServerClient")
    def test_post_batch_forwards_to_syncserver(self, mock_client_cls):
        mock_client = mock.MagicMock()
        mock_client.post.return_value = None
        mock_client_cls.return_value = mock_client

        payload = _valid_batch()
        resp = self._post(
            payload,
            headers={"X-Client-Session-Id": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 204)
        mock_client.post.assert_called_once()
        self.assertEqual(
            mock_client.post.call_args[0][0],
            "/diagnostics/ui-events/batch",
        )
        self.assertEqual(mock_client.post.call_args[1]["json"], payload)

    def test_post_empty_batch_returns_400(self):
        resp = self._post({"events": [], "sent_at": "2026-07-15T10:00:00+00:00", "sequence": 1})
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertEqual(data["error"]["code"], "empty_batch")

    def test_post_invalid_json_returns_400(self):
        req = self.factory.post(
            "/bff/api/v1/diagnostics/ui-events/batch",
            data=b"{not json",
            content_type="application/json",
        )
        resp = self.view(req)
        self.assertEqual(resp.status_code, 400)

    def test_post_invalid_event_type_returns_400(self):
        bad_batch = _valid_batch()
        bad_batch["events"][0]["event_type"] = "made_up_event"
        resp = self._post(bad_batch)
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertEqual(data["error"]["code"], "invalid_event_type")

    def test_post_event_must_be_dict(self):
        bad_batch = _valid_batch()
        bad_batch["events"] = ["not a dict"]
        resp = self._post(bad_batch)
        self.assertEqual(resp.status_code, 400)

    @mock.patch("apps.bff_api.diagnostics_views.SyncServerClient")
    def test_post_oversized_batch_returns_413(self, mock_client_cls):
        # Build a > 100KB body and set content_length
        big_event = _valid_event()
        big_event["details"] = {"x": "y" * 110_000}
        body = json.dumps(_valid_batch()).encode("utf-8") + b' ' * 110_000
        req = self.factory.post(
            "/bff/api/v1/diagnostics/ui-events/batch",
            data=body,
            content_type="application/json",
            CONTENT_LENGTH=str(len(body)),
        )
        resp = self.view(req)
        self.assertEqual(resp.status_code, 413)
        mock_client_cls.assert_not_called()

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    @mock.patch("apps.bff_api.diagnostics_views.SyncServerClient")
    def test_rate_limit_returns_429_after_threshold(self, mock_client_cls):
        mock_client = mock.MagicMock()
        mock_client.post.return_value = None
        mock_client_cls.return_value = mock_client

        session_id = str(uuid4())
        # First 10 requests should pass
        for i in range(10):
            resp = self._post(_valid_batch(), headers={"X-Client-Session-Id": session_id})
            self.assertEqual(resp.status_code, 204, f"req {i+1} failed: {resp.status_code}")
        # 11th should be rate-limited
        resp = self._post(_valid_batch(), headers={"X-Client-Session-Id": session_id})
        self.assertEqual(resp.status_code, 429)
        data = json.loads(resp.content)
        self.assertEqual(data["error"]["code"], "rate_limited")

    @mock.patch("apps.bff_api.diagnostics_views.SyncServerClient")
    def test_upstream_failure_returns_502(self, mock_client_cls):
        mock_client = mock.MagicMock()
        mock_client.post.side_effect = Exception("boom")
        mock_client_cls.return_value = mock_client

        resp = self._post(_valid_batch(), headers={"X-Client-Session-Id": str(uuid4())})
        self.assertEqual(resp.status_code, 502)
        data = json.loads(resp.content)
        self.assertEqual(data["error"]["code"], "upstream_unavailable")

    @mock.patch("apps.bff_api.diagnostics_views.SyncServerClient")
    def test_forwards_x_client_session_id_header(self, mock_client_cls):
        mock_client = mock.MagicMock()
        mock_client.post.return_value = None
        mock_client_cls.return_value = mock_client

        session_id = str(uuid4())
        self._post(_valid_batch(), headers={"X-Client-Session-Id": session_id})
        forwarded = mock_client.post.call_args[1]["extra_headers"]
        self.assertEqual(forwarded["X-Client-Session-Id"], session_id)

    @mock.patch("apps.bff_api.diagnostics_views.SyncServerClient")
    def test_get_request_returns_405(self, mock_client_cls):
        req = self.factory.get("/bff/api/v1/diagnostics/ui-events/batch")
        resp = self.view(req)
        # require_POST decorator returns 405 for non-POST
        self.assertEqual(resp.status_code, 405)
        mock_client_cls.assert_not_called()

    @override_settings(SYNC_SERVER_URL="http://syncserver:8000/api/v1")
    @mock.patch("apps.sync_client.client.resolve_sync_identity")
    @mock.patch("apps.sync_client.client.get_sync_client")
    def test_upstream_url_has_no_doubled_api_v1(self, mock_transport_factory, mock_identity):
        mock_identity.return_value = mock.Mock(user_token="tok-123", source="binding", is_root=False)
        mock_transport = mock.MagicMock()
        mock_transport.request.return_value = mock.MagicMock(status_code=204)
        mock_transport_factory.return_value = mock_transport

        resp = self._post(
            _valid_batch("draft_autosaved"),
            headers={"X-Client-Session-Id": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 204)
        called_url = mock_transport.request.call_args[1]["url"]
        self.assertEqual(
            called_url,
            "http://syncserver:8000/api/v1/diagnostics/ui-events/batch",
        )
        self.assertNotIn("/api/v1/api/v1", called_url)

    @mock.patch("apps.bff_api.diagnostics_views.SyncServerClient")
    def test_draft_event_types_pass_bff_validation(self, mock_client_cls):
        mock_client = mock.MagicMock()
        mock_client.post.return_value = None
        mock_client_cls.return_value = mock_client

        for event_type in ("draft_autosaved", "draft_restored", "draft_lost", "draft_cleared"):
            resp = self._post(
                _valid_batch(event_type),
                headers={"X-Client-Session-Id": str(uuid4())},
            )
            self.assertEqual(resp.status_code, 204, f"{event_type} rejected: {resp.status_code}")

    @override_settings(SYNC_SERVER_URL="http://syncserver:8000/api/v1")
    @mock.patch("apps.sync_client.client.resolve_sync_identity")
    @mock.patch("apps.sync_client.client.get_sync_client")
    def test_forwards_x_request_id_to_syncserver(self, mock_transport_factory, mock_identity):
        mock_identity.return_value = mock.Mock(user_token="tok-123", source="binding", is_root=False)
        mock_transport = mock.MagicMock()
        mock_transport.request.return_value = mock.MagicMock(status_code=204)
        mock_transport_factory.return_value = mock_transport

        request_id = str(uuid4())
        req = self.factory.post(
            "/bff/api/v1/diagnostics/ui-events/batch",
            data=json.dumps(_valid_batch()).encode("utf-8"),
            content_type="application/json",
        )
        req.META["HTTP_X_CLIENT_SESSION_ID"] = str(uuid4())
        req.META["X_REQUEST_ID"] = request_id
        resp = self.view(req)
        self.assertEqual(resp.status_code, 204)
        headers = mock_transport.request.call_args[1]["headers"]
        self.assertEqual(headers["X-Request-Id"], request_id)
