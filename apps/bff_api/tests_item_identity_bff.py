"""BFF regression tests for ADR-0033 (Item Identity Guard) pass-through.

Covers:
- GET /bff/api/v1/catalog/items/identity-candidates proxy (params + empty name);
- structured SyncServer errors forwarded without flattening (candidates kept);
- review-item detail carries the additive identity_candidates field;
- review confirm 409 item_identity_duplicate surfaces code + candidates;
- legacy string-detail 409 on review confirm stays backward-compatible;
- admin item create 409 item_identity_duplicate surfaces code + candidates;
- operations submit ADR-0025 envelope with item_identity_duplicate passes unchanged.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.users.models import Role, SyncUserBinding


def _structured_conflict_payload(
    *,
    message: str = (
        "Товар с таким наименованием, единицей измерения и категорией уже существует. "
        "Подтверждение отклонено — используйте слияние (merge)."
    ),
    candidates: list | None = None,
) -> dict:
    return {
        "detail": {
            "code": "item_identity_duplicate",
            "message": message,
            "candidates": candidates
            or [
                {
                    "id": 42,
                    "name": "Болт М8",
                    "sku": "BOLT-M8",
                    "unit": {"id": 3, "name": "Штука", "symbol": "шт"},
                    "category": {"id": 7, "name": "Крепёж"},
                    "is_active": True,
                    "requires_review": False,
                    "match": "exact",
                }
            ],
        }
    }


class BffApiIdentityCandidatesProxyTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="identity_candidates_root",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.client.force_login(self.user)

    def test_proxy_forwards_name_unit_category_and_returns_ok(self) -> None:
        payload = {"candidates": [{"id": 42, "name": "Болт М8", "match": "exact"}]}
        mock_api = Mock()
        mock_api.get_identity_candidates.return_value = payload

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/catalog/items/identity-candidates",
                {"name": "Болт М8", "unit_id": "3", "category_id": "7"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], payload)
        mock_api.get_identity_candidates.assert_called_once_with(
            name="Болт М8",
            unit_id="3",
            category_id="7",
        )

    def test_proxy_empty_name_still_forwards_name(self) -> None:
        mock_api = Mock()
        mock_api.get_identity_candidates.return_value = {"candidates": []}

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.get("/bff/api/v1/catalog/items/identity-candidates")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], {"candidates": []})
        mock_api.get_identity_candidates.assert_called_once_with(name="")

    def test_proxy_omits_absent_optional_params(self) -> None:
        mock_api = Mock()
        mock_api.get_identity_candidates.return_value = {"candidates": []}

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/catalog/items/identity-candidates",
                {"name": "Болт"},
            )

        self.assertEqual(response.status_code, 200)
        mock_api.get_identity_candidates.assert_called_once_with(name="Болт")

    def test_proxy_sync_error_preserves_structured_detail(self) -> None:
        from apps.sync_client.exceptions import SyncConflictError

        mock_api = Mock()
        mock_api.get_identity_candidates.side_effect = SyncConflictError(
            "Товар с таким наименованием уже существует.",
            status_code=409,
            payload={
                "code": "item_identity_duplicate",
                "message": "Дубль",
                "candidates": [{"id": 1, "name": "x", "match": "exact"}],
            },
        )

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/catalog/items/identity-candidates",
                {"name": "Болт"},
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "item_identity_duplicate")
        self.assertEqual(body["error"]["message"], "Дубль")
        self.assertEqual(body["error"]["candidates"][0]["id"], 1)

    def test_route_registered(self) -> None:
        from apps.bff_api.urls import urlpatterns

        names = {p.name for p in urlpatterns if getattr(p, "name", None)}
        self.assertIn("catalog_identity_candidates", names)


class BffApiReviewItemIdentityTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="identity_review_root",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.client.force_login(self.user)

    def test_review_detail_includes_identity_candidates(self) -> None:
        detail = {
            "id": 42,
            "name": "Болт М8",
            "requires_review": True,
            "identity_candidates": [
                {
                    "id": 7,
                    "name": "Болт М8",
                    "match": "partial",
                    "unit": None,
                    "category": None,
                }
            ],
        }
        mock_api = Mock()
        mock_api.get_review_item.return_value = detail

        with patch("apps.bff_api.review_items_views.ReviewItemsAPI", return_value=mock_api):
            response = self.client.get("/bff/api/v1/review-items/42")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["identity_candidates"], detail["identity_candidates"])

    def test_review_confirm_item_identity_duplicate_surfaces_candidates(self) -> None:
        from apps.sync_client.exceptions import SyncConflictError

        mock_api = Mock()
        mock_api.confirm_review_item.side_effect = SyncConflictError(
            "Товар с таким наименованием уже существует.",
            status_code=409,
            payload=_structured_conflict_payload(),
        )

        with patch("apps.bff_api.review_items_views.ReviewItemsAPI", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/review-items/42/confirm",
                data=json.dumps({"name": "Болт М8"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        error = body["error"]
        self.assertEqual(error["code"], "item_identity_duplicate")
        self.assertEqual(error["candidates"][0]["id"], 42)
        self.assertEqual(error["candidates"][0]["match"], "exact")
        self.assertIn("слияние", error["message"])

    def test_review_confirm_legacy_string_detail_backward_compatible(self) -> None:
        from apps.sync_client.exceptions import SyncConflictError

        mock_api = Mock()
        mock_api.confirm_review_item.side_effect = SyncConflictError(
            "SKU занят",
            status_code=409,
            payload={"detail": "SKU занят"},
        )

        with patch("apps.bff_api.review_items_views.ReviewItemsAPI", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/review-items/42/confirm",
                data=json.dumps({"name": "Болт М8"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        error = body["error"]
        # Legacy string detail keeps the historical `conflict` code and a string message.
        self.assertEqual(error["code"], "conflict")
        self.assertEqual(error["message"], "SKU занят")


class BffApiAdminItemIdentityDuplicateTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="identity_admin_root",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        SyncUserBinding.objects.create(user=self.user, sync_role=Role.CHIEF_STOREKEEPER)
        self.client.force_login(self.user)

    def test_admin_item_create_409_surfaces_candidates(self) -> None:
        from apps.sync_client.exceptions import SyncConflictError

        mock_api = Mock()
        mock_api.create_item.side_effect = SyncConflictError(
            "Товар с таким наименованием уже существует.",
            status_code=409,
            payload=_structured_conflict_payload(),
        )

        with patch("apps.bff_api.catalog_views._catalog", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/items",
                data=json.dumps({"name": "Болт М8"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        error = body["error"]
        self.assertEqual(error["code"], "item_identity_duplicate")
        self.assertEqual(error["candidates"][0]["id"], 42)
        self.assertEqual(error["candidates"][0]["match"], "exact")


class BffApiSubmitIdentityDuplicateEnvelopeTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="identity_submit_root",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.client.force_login(self.user)

    def test_submit_item_identity_duplicate_envelope_passed_through(self) -> None:
        from apps.sync_client.exceptions import SyncConflictError

        envelope = {
            "type": "urn:warehouse:problem:operation-submit-rejected",
            "title": "Операция не может быть проведена",
            "status": 409,
            "code": "operation_submit_rejected",
            "detail": "Товар «Болт М8» уже существует в каталоге (id=42).",
            "instance": "/api/v1/operations/op1/submit",
            "trace_id": "trace-123",
            "errors": [
                {
                    "code": "item_identity_duplicate",
                    "scope": "line_group",
                    "operation_line_ids": [17, 18],
                    "requested_name": "Болт М8",
                    "candidates": [
                        {
                            "id": 42,
                            "name": "Болт М8",
                            "sku": "BOLT-M8",
                            "unit": {"id": 3, "name": "Штука", "symbol": "шт"},
                            "category": {"id": 7, "name": "Крепёж"},
                            "match": "exact",
                        }
                    ],
                }
            ],
        }
        mock_api = Mock()
        mock_api.submit_operation.side_effect = SyncConflictError(
            "Товар уже существует",
            status_code=409,
            payload=envelope,
        )

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations/op1/submit",
                data=json.dumps({"expected_version": 1}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), envelope)
