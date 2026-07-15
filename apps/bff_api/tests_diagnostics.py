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

    @mock.patch("apps.bff_api.diagnostics_views.get_sync_client")
    def test_post_batch_forwards_to_syncserver(self, mock_client_factory):
        mock_client = mock.MagicMock()
        mock_client.post.return_value = mock.MagicMock(status_code=204)
        mock_client_factory.return_value = mock_client

        resp = self._post(
            _valid_batch(),
            headers={"X-Client-Session-Id": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 204)
        mock_client.post.assert_called_once()
        # Verify the URL
        called_url = mock_client.post.call_args[0][0]
        self.assertIn("/api/v1/diagnostics/ui-events/batch", called_url)

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

    @mock.patch("apps.bff_api.diagnostics_views.get_sync_client")
    def test_post_oversized_batch_returns_413(self, mock_client_factory):
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
        mock_client_factory.assert_not_called()

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    @mock.patch("apps.bff_api.diagnostics_views.get_sync_client")
    def test_rate_limit_returns_429_after_threshold(self, mock_client_factory):
        mock_client = mock.MagicMock()
        mock_client.post.return_value = mock.MagicMock(status_code=204)
        mock_client_factory.return_value = mock_client

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

    @mock.patch("apps.bff_api.diagnostics_views.get_sync_client")
    def test_upstream_failure_returns_502(self, mock_client_factory):
        import httpx
        mock_client = mock.MagicMock()
        mock_client.post.side_effect = httpx.HTTPError("boom")
        mock_client_factory.return_value = mock_client

        resp = self._post(_valid_batch(), headers={"X-Client-Session-Id": str(uuid4())})
        self.assertEqual(resp.status_code, 502)
        data = json.loads(resp.content)
        self.assertEqual(data["error"]["code"], "upstream_unavailable")

    @mock.patch("apps.bff_api.diagnostics_views.get_sync_client")
    def test_forwards_x_client_session_id_header(self, mock_client_factory):
        mock_client = mock.MagicMock()
        mock_client.post.return_value = mock.MagicMock(status_code=204)
        mock_client_factory.return_value = mock_client

        session_id = str(uuid4())
        self._post(_valid_batch(), headers={"X-Client-Session-Id": session_id})
        forwarded = mock_client.post.call_args[1]["headers"]
        self.assertEqual(forwarded["X-Client-Session-Id"], session_id)

    @mock.patch("apps.bff_api.diagnostics_views.get_sync_client")
    def test_get_request_returns_405(self, mock_client_factory):
        req = self.factory.get("/bff/api/v1/diagnostics/ui-events/batch")
        resp = self.view(req)
        # require_POST decorator returns 405 for non-POST
        self.assertEqual(resp.status_code, 405)
