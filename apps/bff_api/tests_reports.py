from __future__ import annotations

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase


class BffApiItemMovementPassthroughTests(TestCase):
    """A-6 (ADR-0028 §7): ItemMovementView only forwards explicit
    exclude_system_effects from the query allow-list. It never invents a default
    and never interprets the boolean value."""

    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="reports_bff_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.client.force_login(self.user)

    def _stub_client(self) -> Mock:
        mock_client = Mock()
        mock_client.get.return_value = {"items": [], "total_count": 0, "page": 1, "page_size": 100}
        return mock_client

    def test_explicit_true_forwarded_unchanged(self) -> None:
        mock_client = self._stub_client()
        with patch("apps.bff_api.reports_views._build_client", return_value=mock_client):
            response = self.client.get(
                "/bff/api/v1/reports/item-movement",
                {"exclude_system_effects": "true", "page": "1"},
            )

        self.assertEqual(response.status_code, 200)
        mock_client.get.assert_called_once_with(
            "/reports/item-movement",
            params={"exclude_system_effects": "true", "page": "1"},
        )

    def test_explicit_false_forwarded_unchanged(self) -> None:
        mock_client = self._stub_client()
        with patch("apps.bff_api.reports_views._build_client", return_value=mock_client):
            response = self.client.get(
                "/bff/api/v1/reports/item-movement",
                {"exclude_system_effects": "false", "site_id": "2"},
            )

        self.assertEqual(response.status_code, 200)
        mock_client.get.assert_called_once_with(
            "/reports/item-movement",
            params={"exclude_system_effects": "false", "site_id": "2"},
        )

    def test_omitted_param_remains_omitted(self) -> None:
        mock_client = self._stub_client()
        with patch("apps.bff_api.reports_views._build_client", return_value=mock_client):
            response = self.client.get(
                "/bff/api/v1/reports/item-movement",
                {"site_id": "1", "page_size": "50"},
            )

        self.assertEqual(response.status_code, 200)
        mock_client.get.assert_called_once_with(
            "/reports/item-movement",
            params={"site_id": "1", "page_size": "50"},
        )

    def test_unrelated_params_unchanged(self) -> None:
        mock_client = self._stub_client()
        forwarded = {
            "site_id": "1",
            "search": "дрель",
            "date_from": "2026-01-01",
            "page": "2",
            "exclude_system_effects": "false",
        }
        with patch("apps.bff_api.reports_views._build_client", return_value=mock_client):
            response = self.client.get(
                "/bff/api/v1/reports/item-movement",
                forwarded,
            )

        self.assertEqual(response.status_code, 200)
        mock_client.get.assert_called_once_with(
            "/reports/item-movement",
            params=forwarded,
        )
