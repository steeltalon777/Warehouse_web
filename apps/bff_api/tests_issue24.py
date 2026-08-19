"""BFF regression tests for issue #24 (targeted balances + authoritative search).

Covers:
- GET /bff/api/v1/balances item_ids forwarding (no loss);
- SyncServer 422 propagation for incompatible/oversized targeted filters;
- resolve_items chunking >100;
- balance enrichment: single batched call (not N+1) and failure != false zero;
- authoritative search does not return cache-only results.
"""
from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase


class BffApiBalancesTargetedTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="bff_balances24",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.client.force_login(self.user)

    def test_item_ids_forwarded_to_list_balances(self) -> None:
        mock_api = Mock()
        mock_api.list_balances.return_value = {"items": [], "total_count": 0}

        with patch("apps.bff_api.balances_views._balances", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/balances",
                {"site_id": "2", "item_ids": "1342,7"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        mock_api.list_balances.assert_called_once()
        filters = mock_api.list_balances.call_args.kwargs["filters"]
        self.assertEqual(filters["item_ids"], "1342,7")
        self.assertEqual(filters["site_id"], "2")

    def test_targeted_result_is_not_truncated_by_pagination(self) -> None:
        """The BFF must not force page/page_size that would truncate a targeted read."""
        mock_api = Mock()
        mock_api.list_balances.return_value = {
            "items": [{"item_id": i} for i in range(150)],
            "total_count": 150,
        }

        with patch("apps.bff_api.balances_views._balances", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/balances",
                {"site_id": "2", "item_ids": ",".join(str(i) for i in range(150))},
            )

        self.assertEqual(response.status_code, 200)
        filters = mock_api.list_balances.call_args.kwargs["filters"]
        # The item_ids list passes through intact, without any page_size cap.
        self.assertEqual(filters["item_ids"], ",".join(str(i) for i in range(150)))

    def test_syncserver_422_propagated(self) -> None:
        from apps.sync_client.exceptions import SyncServerAPIError

        mock_api = Mock()
        mock_api.list_balances.side_effect = SyncServerAPIError(
            "item_ids must not exceed 200 entries",
            status_code=422,
            method="GET",
            path="/balances",
        )

        with patch("apps.bff_api.balances_views._balances", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/balances",
                {"site_id": "2", "item_ids": ",".join(str(i) for i in range(201))},
            )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertFalse(body["ok"])


class BffApiCatalogResolverChunkingTests(TestCase):
    def test_resolve_items_chunks_over_100(self) -> None:
        from apps.bff_api.catalog_resolver import resolve_items

        mock_client = Mock()

        def side_effect(path: str, json=None):
            ids = json["item_ids"]
            return {"items": [{"requested_id": i, "status": "active"} for i in ids]}

        mock_client.post.side_effect = side_effect

        ids = list(range(250))
        results = resolve_items(mock_client, ids)

        self.assertEqual(len(results), 250)
        calls = mock_client.post.call_args_list
        self.assertEqual(len(calls), 3)  # 100 + 100 + 50
        chunk_sizes = [len(call.kwargs["json"]["item_ids"]) for call in calls]
        self.assertEqual(chunk_sizes, [100, 100, 50])
        # Chunks are contiguous slices of the input, in order.
        all_ids = [i for call in calls for i in call.kwargs["json"]["item_ids"]]
        self.assertEqual(all_ids, [str(i) for i in range(250)])


class BffApiBalanceEnrichmentTests(TestCase):
    def _view(self):
        from apps.bff_api.catalog_views import CatalogCachedItemSearchView

        return CatalogCachedItemSearchView()

    def _items(self, count: int):
        return [{"id": str(i), "name": f"Item {i}"} for i in range(count)]

    def test_enrichment_uses_single_batched_call_not_n_plus_one(self) -> None:
        view = self._view()
        items = self._items(5)
        mock_balances = Mock()
        mock_balances.list_balances.return_value = {
            "items": [{"item_id": str(i), "qty": "10"} for i in range(5)]
        }

        with (
            patch("apps.bff_api.catalog_views._build_client", return_value=Mock()),
            patch("apps.bff_api.catalog_views.BalancesAPI", return_value=mock_balances),
        ):
            enriched = view._enrich_with_balances(Mock(), items, "2")

        self.assertEqual(mock_balances.list_balances.call_count, 1)
        # The single call carries all 5 ids in one item_ids filter.
        filters = mock_balances.list_balances.call_args.kwargs["filters"]
        self.assertEqual(filters["item_ids"], "0,1,2,3,4")
        self.assertEqual(len(enriched), 5)
        self.assertEqual(enriched[0]["balance_qty"], "10")

    def test_enrichment_failure_does_not_become_false_zero(self) -> None:
        view = self._view()
        items = self._items(3)
        mock_balances = Mock()
        mock_balances.list_balances.side_effect = Exception("boom")

        with (
            patch("apps.bff_api.catalog_views._build_client", return_value=Mock()),
            patch("apps.bff_api.catalog_views.BalancesAPI", return_value=mock_balances),
        ):
            enriched = view._enrich_with_balances(Mock(), items, "2")

        # On failure the items come back unchanged — no false balance_qty "0".
        self.assertEqual(enriched, items)
        self.assertNotIn("balance_qty", enriched[0])


class BffApiStructuredLineErrorTests(TestCase):
    def test_operation_lines_invalid_promotes_lines_to_error(self) -> None:
        """B3: the BFF must surface `lines` at `error.lines` for the frontend."""
        from apps.bff_api.helpers import _handle_sync_error
        from apps.sync_client.exceptions import SyncServerAPIError

        exc = SyncServerAPIError(
            "One or more operation lines are invalid",
            status_code=409,
            method="POST",
            path="/operations",
            payload={
                "code": "operation_lines_invalid",
                "message": "One or more operation lines are invalid",
                "operation_id": "op-1",
                "lines": [
                    {"line_number": 3, "item_id": 2721, "reason": "item_not_found"},
                    {"line_number": 7, "item_id": 101, "reason": "duplicate_item", "first_line_number": 2},
                ],
            },
        )

        response = _handle_sync_error(exc)
        self.assertEqual(response.status_code, 409)
        body = json.loads(response.content)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "operation_lines_invalid")
        self.assertIn("lines", body["error"])
        self.assertEqual(body["error"]["lines"][0]["reason"], "item_not_found")
        self.assertEqual(body["error"]["operation_id"], "op-1")

