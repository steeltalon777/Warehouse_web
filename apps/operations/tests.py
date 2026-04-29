from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.forms import ItemForm
from apps.catalog.services import ServiceResult
from apps.catalog_cache.models import CatalogCacheItem
from apps.operations.forms import validate_acceptance_lines, validate_lost_asset_resolve
from apps.operations.services import OperationPageService
from apps.operations.views import (
    _build_create_payload,
    _get_post_list,
    _load_pending_acceptance_for_operation,
)
from apps.sync_client.exceptions import SyncServerAPIError


class OperationCreatePayloadQuantityTests(SimpleTestCase):
    def test_create_payload_includes_effective_at_and_decimal_quantity(self) -> None:
        payload = _build_create_payload(
            {
                "operation_type": "RECEIVE",
                "site_id": 1,
                "effective_at": "2026-04-21T16:15",
                "items": [{"item_id": 10, "quantity": "1.250"}],
            },
            operate_site_ids={1},
        )

        self.assertEqual(payload["effective_at"], "2026-04-21T07:15:00Z")
        self.assertEqual(payload["lines"][0]["qty"], "1.25")

    def test_create_payload_accepts_decimal_quantity(self) -> None:
        payload = _build_create_payload(
            {
                "operation_type": "RECEIVE",
                "site_id": 1,
                "items": [{"item_id": 10, "quantity": "1.250"}],
            },
            operate_site_ids={1},
        )

        self.assertEqual(payload["lines"][0]["qty"], "1.25")

    def test_create_payload_accepts_negative_decimal_for_adjustment(self) -> None:
        payload = _build_create_payload(
            {
                "operation_type": "ADJUSTMENT",
                "site_id": 1,
                "items": [{"item_id": 10, "quantity": "-0.125"}],
            },
            operate_site_ids={1},
        )

        self.assertEqual(payload["lines"][0]["qty"], "-0.125")

    def test_move_allows_destination_outside_operate_sites_when_visible(self) -> None:
        payload = _build_create_payload(
            {
                "operation_type": "MOVE",
                "source_site_id": 1,
                "destination_site_id": 2,
                "items": [{"item_id": 10, "quantity": "1"}],
            },
            operate_site_ids={1},
            destination_site_ids={1, 2},
        )

        self.assertEqual(payload["source_site_id"], 1)
        self.assertEqual(payload["destination_site_id"], 2)

    def test_move_rejects_destination_missing_from_visible_sites(self) -> None:
        with self.assertRaisesMessage(ValidationError, "склад-получатель"):
            _build_create_payload(
                {
                    "operation_type": "MOVE",
                    "source_site_id": 1,
                    "destination_site_id": 2,
                    "items": [{"item_id": 10, "quantity": "1"}],
                },
                operate_site_ids={1},
                destination_site_ids={1},
            )

    def test_create_payload_rejects_more_than_three_decimal_places(self) -> None:
        with self.assertRaisesMessage(ValidationError, "точностью до 3 знаков"):
            _build_create_payload(
                {
                    "operation_type": "RECEIVE",
                    "site_id": 1,
                    "items": [{"item_id": 10, "quantity": "1.2345"}],
                },
                operate_site_ids={1},
            )

    def test_create_payload_with_temporary_items_generates_client_request_id(self) -> None:
        payload = _build_create_payload(
            {
                "operation_type": "RECEIVE",
                "site_id": 1,
                "items": [
                    {
                        "kind": "temporary",
                        "name": "Кабель ВВГ",
                        "sku": "VVG-1",
                        "category_id": 7,
                        "unit_id": 3,
                        "description": "Кабель силовой",
                        "quantity": "5.000"
                    }
                ],
            },
            operate_site_ids={1},
        )

        self.assertIn("client_request_id", payload)
        self.assertIsInstance(payload["client_request_id"], str)
        self.assertEqual(len(payload["client_request_id"]), 36)  # UUID length
        self.assertEqual(payload["lines"][0]["temporary_item"]["name"], "Кабель ВВГ")
        self.assertEqual(payload["lines"][0]["temporary_item"]["sku"], "VVG-1")
        self.assertEqual(payload["lines"][0]["temporary_item"]["category_id"], 7)
        self.assertEqual(payload["lines"][0]["temporary_item"]["unit_id"], 3)
        self.assertEqual(payload["lines"][0]["temporary_item"]["description"], "Кабель силовой")
        self.assertEqual(payload["lines"][0]["qty"], "5")

    def test_create_payload_with_mixed_items_generates_client_request_id(self) -> None:
        payload = _build_create_payload(
            {
                "operation_type": "RECEIVE",
                "site_id": 1,
                "items": [
                    {
                        "kind": "catalog",
                        "item_id": 10,
                        "quantity": "2.500"
                    },
                    {
                        "kind": "temporary",
                        "name": "Кабель ВВГ",
                        "sku": "VVG-1",
                        "category_id": 7,
                        "unit_id": 3,
                        "quantity": "1.000"
                    }
                ],
            },
            operate_site_ids={1},
        )

        self.assertIn("client_request_id", payload)
        self.assertEqual(len(payload["client_request_id"]), 36)
        self.assertEqual(len(payload["lines"]), 2)
        self.assertEqual(payload["lines"][0]["item_id"], 10)
        self.assertEqual(payload["lines"][0]["qty"], "2.5")
        self.assertEqual(payload["lines"][1]["temporary_item"]["name"], "Кабель ВВГ")
        self.assertEqual(payload["lines"][1]["qty"], "1")

    def test_create_payload_with_only_catalog_items_no_client_request_id(self) -> None:
        payload = _build_create_payload(
            {
                "operation_type": "RECEIVE",
                "site_id": 1,
                "items": [
                    {
                        "kind": "catalog",
                        "item_id": 10,
                        "quantity": "3.000"
                    }
                ],
            },
            operate_site_ids={1},
        )

        self.assertNotIn("client_request_id", payload)
        self.assertEqual(payload["lines"][0]["item_id"], 10)
        self.assertEqual(payload["lines"][0]["qty"], "3")

    def test_create_payload_backward_compatibility_without_kind(self) -> None:
        # Старый формат без поля kind - должен определяться автоматически
        payload = _build_create_payload(
            {
                "operation_type": "RECEIVE",
                "site_id": 1,
                "items": [
                    {
                        "item_id": 10,
                        "quantity": "2.000"
                    }
                ],
            },
            operate_site_ids={1},
        )

        self.assertNotIn("client_request_id", payload)
        self.assertEqual(payload["lines"][0]["item_id"], 10)
        self.assertEqual(payload["lines"][0]["qty"], "2")

    def test_create_payload_temporary_item_requires_name_and_sku(self) -> None:
        with self.assertRaisesMessage(ValidationError, "Для временной ТМЦ укажите наименование."):
            _build_create_payload(
                {
                    "operation_type": "RECEIVE",
                    "site_id": 1,
                    "items": [
                        {
                            "kind": "temporary",
                            "category_id": 7,
                            "unit_id": 3,
                            "quantity": "1.000"
                        }
                    ],
                },
                operate_site_ids={1},
            )

    def test_create_payload_temporary_item_requires_category_and_unit(self) -> None:
        with self.assertRaisesMessage(ValidationError, "Для временной ТМЦ выберите единицу измерения."):
            _build_create_payload(
                {
                    "operation_type": "RECEIVE",
                    "site_id": 1,
                    "items": [
                        {
                            "kind": "temporary",
                            "name": "Кабель",
                            "sku": "CBL-1",
                            "quantity": "1.000"
                        }
                    ],
                },
                operate_site_ids={1},
            )


class OperationPageServiceSearchTests(TestCase):
    def test_search_items_supplements_cache_with_remote_results(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="101",
            name="Cable FTP",
            sku="FTP-1",
            search_text="cable ftp ftp-1 networking",
            category_id="10",
            category_name="Networking",
            unit_symbol="m",
            is_active=True,
            source_updated_at=now,
            synced_at=now,
        )

        service = OperationPageService(client=Mock())
        service.catalog.browse_items = Mock(
            return_value=ServiceResult(
                ok=True,
                data={
                    "items": [
                        {
                            "id": 202,
                            "name": "Cable UTP",
                            "sku": "UTP-5E",
                            "category_id": 10,
                            "category_name": "Networking",
                            "unit_symbol": "m",
                            "is_active": True,
                        }
                    ]
                },
            )
        )

        items = service.search_items("cable", limit=10)

        self.assertEqual([item["id"] for item in items], [101, 202])
        cached = CatalogCacheItem.objects.get(sync_id="202")
        self.assertEqual(cached.name, "Cable UTP")
        self.assertEqual(cached.sku, "UTP-5E")

    def test_search_items_keeps_local_results_when_remote_lookup_fails(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="101",
            name="Cable FTP",
            sku="FTP-1",
            search_text="cable ftp ftp-1 networking",
            category_id="10",
            category_name="Networking",
            unit_symbol="m",
            is_active=True,
            source_updated_at=now,
            synced_at=now,
        )

        service = OperationPageService(client=Mock())
        service.catalog.browse_items = Mock(return_value=ServiceResult(ok=False, form_error="sync failed"))

        items = service.search_items("cable", limit=10)

        self.assertEqual([item["id"] for item in items], [101])

    def test_search_items_returns_empty_list_when_remote_lookup_fails_without_cache(self) -> None:
        service = OperationPageService(client=Mock())
        service.catalog.browse_items = Mock(side_effect=SyncServerAPIError("sync unavailable", status_code=502))

        items = service.search_items("missing", limit=10)

        self.assertEqual(items, [])


class ItemFormDefaultUnitTests(SimpleTestCase):
    def test_item_form_sets_default_unit_to_piece_when_available(self) -> None:
        form = ItemForm(units=[{"id": 3, "name": "Штука", "symbol": "шт"}])

        self.assertEqual(form.initial["unit_id"], "3")

    def test_item_form_does_not_fail_when_piece_unit_missing(self) -> None:
        form = ItemForm(units=[{"id": 4, "name": "Метр", "symbol": "м"}])

        self.assertNotIn("unit_id", form.initial)


class ValidateAcceptanceLinesTests(SimpleTestCase):
    """Tests for validate_acceptance_lines form validator."""

    def test_valid_full_acceptance(self) -> None:
        remaining = {1: Decimal("10.000"), 2: Decimal("5.000")}
        raw_lines = [
            {"line_number": 1, "accepted_qty": "10.000", "lost_qty": "0", "note": ""},
            {"line_number": 2, "accepted_qty": "5.000", "lost_qty": "0", "note": ""},
        ]
        result = validate_acceptance_lines(raw_lines, remaining_by_line=remaining)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["line_id"], 1)
        self.assertEqual(result[1]["line_id"], 2)
        # _serialize_decimal normalizes "10.000" -> "10"
        self.assertEqual(result[0]["accepted_qty"], "10")
        self.assertEqual(result[1]["accepted_qty"], "5")

    def test_partial_acceptance_with_loss(self) -> None:
        remaining = {1: Decimal("10.000")}
        raw_lines = [
            {"line_number": 1, "accepted_qty": "8.000", "lost_qty": "2.000", "note": "Повреждение"},
        ]
        result = validate_acceptance_lines(raw_lines, remaining_by_line=remaining)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["line_id"], 1)
        self.assertEqual(result[0]["accepted_qty"], "8")
        self.assertEqual(result[0]["lost_qty"], "2")
        self.assertEqual(result[0]["note"], "Повреждение")

    def test_skips_unchanged_lines(self) -> None:
        remaining = {1: Decimal("10.000")}
        raw_lines = [
            {"line_number": 1, "accepted_qty": "0", "lost_qty": "0", "note": ""},
        ]
        result = validate_acceptance_lines(raw_lines, remaining_by_line=remaining)
        self.assertEqual(len(result), 0)

    def test_rejects_negative_accepted_qty(self) -> None:
        remaining = {1: Decimal("10.000")}
        raw_lines = [
            {"line_number": 1, "accepted_qty": "-1", "lost_qty": "0", "note": ""},
        ]
        with self.assertRaises(ValidationError):
            validate_acceptance_lines(raw_lines, remaining_by_line=remaining)

    def test_rejects_sum_exceeding_remaining(self) -> None:
        remaining = {1: Decimal("10.000")}
        raw_lines = [
            {"line_number": 1, "accepted_qty": "10.000", "lost_qty": "1.000", "note": ""},
        ]
        with self.assertRaises(ValidationError):
            validate_acceptance_lines(raw_lines, remaining_by_line=remaining)

    def test_rejects_negative_lost_qty(self) -> None:
        remaining = {1: Decimal("10.000")}
        raw_lines = [
            {"line_number": 1, "accepted_qty": "5", "lost_qty": "-1", "note": ""},
        ]
        with self.assertRaises(ValidationError):
            validate_acceptance_lines(raw_lines, remaining_by_line=remaining)


class ValidateLostAssetResolveTests(SimpleTestCase):
    """Tests for validate_lost_asset_resolve form validator."""

    def test_valid_found_to_destination(self) -> None:
        payload = validate_lost_asset_resolve(
            {"action": "found_to_destination", "qty": "5.000", "note": "Найден", "responsible_recipient_id": ""},
            max_qty=Decimal("10.000"),
            has_source_site=True,
        )
        self.assertEqual(payload["action"], "found_to_destination")
        # _serialize_decimal normalizes "5.000" -> "5"
        self.assertEqual(payload["qty"], "5")

    def test_valid_return_to_source(self) -> None:
        payload = validate_lost_asset_resolve(
            {"action": "return_to_source", "qty": "3.000", "note": "Возврат", "responsible_recipient_id": "42"},
            max_qty=Decimal("10.000"),
            has_source_site=True,
        )
        self.assertEqual(payload["action"], "return_to_source")
        # responsible_recipient_id is cast to int
        self.assertEqual(payload["responsible_recipient_id"], 42)

    def test_rejects_return_to_source_without_source_site(self) -> None:
        with self.assertRaises(ValidationError):
            validate_lost_asset_resolve(
                {"action": "return_to_source", "qty": "1", "note": "", "responsible_recipient_id": ""},
                max_qty=Decimal("10.000"),
                has_source_site=False,
            )

    def test_rejects_invalid_action(self) -> None:
        with self.assertRaises(ValidationError):
            validate_lost_asset_resolve(
                {"action": "invalid_action", "qty": "1", "note": "", "responsible_recipient_id": ""},
                max_qty=Decimal("10.000"),
                has_source_site=True,
            )

    def test_rejects_qty_exceeding_max(self) -> None:
        with self.assertRaises(ValidationError):
            validate_lost_asset_resolve(
                {"action": "found_to_destination", "qty": "20.000", "note": "", "responsible_recipient_id": ""},
                max_qty=Decimal("10.000"),
                has_source_site=True,
            )

    def test_rejects_zero_qty(self) -> None:
        with self.assertRaises(ValidationError):
            validate_lost_asset_resolve(
                {"action": "write_off", "qty": "0", "note": "", "responsible_recipient_id": ""},
                max_qty=Decimal("10.000"),
                has_source_site=True,
            )


class GroupPendingRowsTests(SimpleTestCase):
    """Tests for OperationPageService.group_pending_rows."""

    def setUp(self) -> None:
        self.service = OperationPageService(client=Mock())

    def test_groups_by_operation_id(self) -> None:
        rows = [
            {"operation_id": "op1", "line_number": 1, "qty": "10.000", "destination_site_id": 5},
            {"operation_id": "op1", "line_number": 2, "qty": "5.000", "destination_site_id": 5},
            {"operation_id": "op2", "line_number": 1, "qty": "3.000", "destination_site_id": 7},
        ]
        groups = self.service.group_pending_rows(rows)
        self.assertEqual(len(groups), 2)
        op1 = [g for g in groups if g["operation_id"] == "op1"][0]
        op2 = [g for g in groups if g["operation_id"] == "op2"][0]
        self.assertEqual(op1["line_count"], 2)
        # _serialize_decimal normalizes "15.000" -> "15"
        self.assertEqual(op1["total_expected_qty"], "15")
        self.assertEqual(op2["line_count"], 1)
        self.assertEqual(op2["total_expected_qty"], "3")

    def test_detects_move_type(self) -> None:
        rows = [
            {"operation_id": "op1", "line_number": 1, "qty": "10.000",
             "source_site_id": 2, "destination_site_id": 5},
        ]
        groups = self.service.group_pending_rows(rows)
        self.assertEqual(groups[0]["operation_type"], "MOVE")

    def test_detects_receive_type(self) -> None:
        rows = [
            {"operation_id": "op1", "line_number": 1, "qty": "10.000",
             "source_site_id": None, "destination_site_id": 5},
        ]
        groups = self.service.group_pending_rows(rows)
        self.assertEqual(groups[0]["operation_type"], "RECEIVE")

    def test_returns_empty_list_for_no_rows(self) -> None:
        groups = self.service.group_pending_rows([])
        self.assertEqual(groups, [])


class ComputePendingSummaryTests(SimpleTestCase):
    """Tests for OperationPageService.compute_pending_summary."""

    def setUp(self) -> None:
        self.service = OperationPageService(client=Mock())

    def test_summary_counts(self) -> None:
        rows = [
            {"operation_id": "op1", "line_number": 1, "qty": "10.000", "destination_site_id": 5},
            {"operation_id": "op1", "line_number": 2, "qty": "5.000", "destination_site_id": 5},
            {"operation_id": "op2", "line_number": 1, "qty": "3.000", "destination_site_id": 7},
        ]
        summary = self.service.compute_pending_summary(rows)
        self.assertEqual(summary["operation_count"], 2)
        self.assertEqual(summary["line_count"], 3)

    def test_summary_by_destination_site(self) -> None:
        rows = [
            {"operation_id": "op1", "line_number": 1, "qty": "10.000", "destination_site_id": 5,
             "destination_site_name": "Site A"},
            {"operation_id": "op2", "line_number": 1, "qty": "3.000", "destination_site_id": 7,
             "destination_site_name": "Site B"},
        ]
        summary = self.service.compute_pending_summary(rows)
        # site_name is resolved from sites_index (Mock returns empty), not from row
        self.assertEqual(len(summary["by_destination_site"]), 2)
        site_ids = {s["site_id"] for s in summary["by_destination_site"]}
        self.assertIn(5, site_ids)
        self.assertIn(7, site_ids)

    def test_truncated_flag(self) -> None:
        summary = self.service.compute_pending_summary([], truncated=True)
        self.assertTrue(summary["truncated"])


class PresentAcceptanceDetailTests(SimpleTestCase):
    """Tests for OperationPageService.present_acceptance_detail."""

    def setUp(self) -> None:
        self.service = OperationPageService(client=Mock())

    def test_presents_header_and_lines(self) -> None:
        operation = {"id": "op1", "document_number": "DOC-001", "operation_type": "RECEIVE"}
        rows = [
            {"line_number": 1, "item_id": 101, "item_name": "Товар A",
             "qty": "10.000", "accepted_qty": None, "lost_qty": None, "note": None},
        ]
        result = self.service.present_acceptance_detail(operation, rows)
        # Header fields are at top level, not nested under "header"
        self.assertEqual(result["document_number"], "DOC-001")
        self.assertEqual(result["flow_state"], "in_progress")
        self.assertEqual(len(result["lines"]), 1)
        self.assertEqual(result["lines"][0]["expected_qty"], "10")
        self.assertTrue(result["lines"][0]["can_accept"])

    def test_flow_state_resolved_when_all_accepted(self) -> None:
        operation = {"id": "op1", "document_number": "DOC-001", "operation_type": "RECEIVE"}
        rows = [
            {"line_number": 1, "item_id": 101, "item_name": "Товар A",
             "qty": "10.000", "accepted_qty": "10.000", "lost_qty": "0", "note": "",
             "remaining_qty": "0"},
        ]
        result = self.service.present_acceptance_detail(operation, rows)
        self.assertEqual(result["flow_state"], "resolved")

    def test_has_lost_flag(self) -> None:
        operation = {"id": "op1", "document_number": "DOC-001", "operation_type": "RECEIVE"}
        rows = [
            {"line_number": 1, "item_id": 101, "item_name": "Товар A",
             "qty": "10.000", "accepted_qty": "8.000", "lost_qty": "2.000", "note": ""},
        ]
        result = self.service.present_acceptance_detail(operation, rows)
        self.assertTrue(result["has_lost"])


class PendingAcceptanceLoadingTests(SimpleTestCase):
    def test_loads_operation_rows_with_api_page_limit(self) -> None:
        assets_api = Mock()
        assets_api.list_pending_acceptance_all_pages.return_value = {"items": []}

        result = _load_pending_acceptance_for_operation(assets_api, "op-1")

        self.assertEqual(result, {"items": []})
        assets_api.list_pending_acceptance_all_pages.assert_called_once_with(
            filters={"operation_id": "op-1"},
            max_rows=200,
        )

    def test_accepts_bracketed_form_list_fields(self) -> None:
        request = Mock()
        request.POST.getlist.side_effect = lambda name: {
            "line_number": [],
            "line_number[]": ["1", "2"],
        }.get(name, [])

        self.assertEqual(_get_post_list(request, "line_number"), ["1", "2"])

    def test_present_acceptance_detail_uses_operation_line_id_as_fallback_number(self) -> None:
        service = OperationPageService(client=Mock())
        operation = {"id": "op1", "document_number": "DOC-001", "operation_type": "RECEIVE"}
        rows = [{"operation_line_id": 42, "item_id": 101, "qty": "10.000"}]

        result = service.present_acceptance_detail(operation, rows)

        self.assertEqual(result["lines"][0]["operation_line_id"], 42)
        self.assertEqual(result["lines"][0]["line_number"], 42)


class PresentLostAssetDetailTests(SimpleTestCase):
    """Tests for OperationPageService.present_lost_asset_detail."""

    def setUp(self) -> None:
        self.service = OperationPageService(client=Mock())

    def test_presents_lost_asset(self) -> None:
        lost_asset = {
            "operation_line_id": "line-1",
            "item_id": 101,
            "item_name": "Товар A",
            "qty": "5.000",
            "operation_id": "op1",
            "status": "open",
        }
        result = self.service.present_lost_asset_detail(lost_asset)
        self.assertEqual(result["operation_line_id"], "line-1")
        # _serialize_decimal normalizes "5.000" -> "5"
        self.assertEqual(result["lost_qty"], "5")
        self.assertEqual(result["status"], "open")

    def test_available_actions_includes_found_to_destination(self) -> None:
        lost_asset = {"operation_line_id": "line-1", "qty": "5.000", "status": "open"}
        result = self.service.present_lost_asset_detail(lost_asset)
        # available_actions is a list of strings (action values)
        self.assertIn("found_to_destination", result["available_actions"])
        self.assertIn("write_off", result["available_actions"])

    def test_available_actions_includes_return_to_source_when_source_exists(self) -> None:
        lost_asset = {
            "operation_line_id": "line-1", "qty": "5.000", "status": "open",
            "source_site_id": 2,
        }
        result = self.service.present_lost_asset_detail(lost_asset)
        self.assertIn("return_to_source", result["available_actions"])

    def test_no_available_actions_when_resolved(self) -> None:
        lost_asset = {
            "operation_line_id": "line-1", "qty": "5.000", "status": "resolved",
            "resolved_action": "found_to_destination",
        }
        result = self.service.present_lost_asset_detail(lost_asset)
        self.assertEqual(result["available_actions"], [])


class PresentOperationSnapshotTests(SimpleTestCase):
    """Тесты для _present_operation с snapshot-полями и временными ТМЦ."""

    def setUp(self) -> None:
        self.service = OperationPageService(client=Mock())
        self.service.request = Mock()
        self.service.request.user = Mock()
        self.service.request.user.sync_binding = Mock()
        self.service.request.user.sync_binding.syncserver_user_id = 123

    def test_snapshot_fields_priority(self) -> None:
        """Snapshot-поля должны иметь приоритет над данными каталога."""
        items_index = {
            101: {"name": "Текущее имя", "sku": "CURRENT-SKU", "unit_symbol": "шт"}
        }
        operation = {
            "id": "op1",
            "operation_type": "RECEIVE",
            "status": "draft",
            "site_id": 1,
            "lines": [
                {
                    "line_number": 1,
                    "item_id": 101,
                    "item_name_snapshot": "Историческое имя",
                    "item_sku_snapshot": "HIST-SKU",
                    "unit_symbol_snapshot": "кг",
                    "qty": "5.000",
                    "comment": "тест",
                }
            ]
        }
        presented = self.service._present_operation(
            operation,
            items_index=items_index,
            sites_index={1: {"site_id": 1, "name": "Склад 1"}}
        )
        line = presented["lines"][0]
        self.assertEqual(line["item_name"], "Историческое имя")
        self.assertEqual(line["sku"], "HIST-SKU")
        self.assertEqual(line["unit_symbol"], "кг")
        self.assertFalse(line["is_temporary"])
        self.assertIsNone(line["temporary_item_id"])

    def test_acceptance_state_labels(self) -> None:
        operation = {
            "id": "op4",
            "operation_type": "RECEIVE",
            "status": "submitted",
            "site_id": 1,
            "acceptance_state": "resolved",
            "lines": [],
        }

        presented = self.service._present_operation(
            operation,
            items_index={},
            sites_index={1: {"site_id": 1, "name": "Склад 1"}},
        )

        self.assertEqual(presented["acceptance_state_label"], "Приёмка завершена")
        self.assertEqual(presented["acceptance_state_tone"], "success")

    def test_acceptance_not_required_label(self) -> None:
        operation = {
            "id": "op5",
            "operation_type": "EXPENSE",
            "status": "submitted",
            "site_id": 1,
            "acceptance_state": "not_required",
            "lines": [],
        }

        presented = self.service._present_operation(
            operation,
            items_index={},
            sites_index={1: {"site_id": 1, "name": "Склад 1"}},
        )

        self.assertEqual(presented["acceptance_state_label"], "Не требуется")
        self.assertEqual(presented["acceptance_state_tone"], "muted")

    def test_get_sites_index_uses_global_site_catalog(self) -> None:
        service = OperationPageService(client=Mock(), request=Mock())

        with patch("apps.operations.services.SyncServerClient") as client_cls:
            root_client = client_cls.return_value
            root_client.get.return_value = {
                "sites": [
                    {"site_id": 1, "name": "Склад A", "permissions": {"can_operate": True}},
                    {"site_id": 2, "name": "Склад B", "permissions": {"can_operate": False}},
                ]
            }

            sites_index = service.get_sites_index()

        client_cls.assert_called_once_with(request=service.request, force_root=True)
        root_client.get.assert_called_once_with("/catalog/sites")
        self.assertEqual(sites_index[2]["name"], "Склад B")

    def test_temporary_item_flags(self) -> None:
        """Строки с temporary_item_id должны помечаться как временные."""
        items_index = {}
        operation = {
            "id": "op2",
            "operation_type": "RECEIVE",
            "status": "draft",
            "site_id": 1,
            "lines": [
                {
                    "line_number": 1,
                    "item_id": None,
                    "temporary_item_id": 500,
                    "item_name_snapshot": "Временный товар",
                    "item_sku_snapshot": "",
                    "unit_symbol_snapshot": "м",
                    "qty": "2.000",
                    "comment": "",
                    "resolved_item_id": 201,
                    "resolved_item_name": "Постоянный товар",
                }
            ]
        }
        presented = self.service._present_operation(
            operation,
            items_index=items_index,
            sites_index={1: {"site_id": 1, "name": "Склад 1"}}
        )
        line = presented["lines"][0]
        self.assertTrue(line["is_temporary"])
        self.assertEqual(line["temporary_item_id"], 500)
        self.assertEqual(line["resolved_item_id"], 201)
        self.assertEqual(line["resolved_item_name"], "Постоянный товар")
        self.assertEqual(line["item_name"], "Временный товар")
        self.assertEqual(line["unit_symbol"], "м")

    def test_missing_snapshot_falls_back_to_catalog(self) -> None:
        """Если snapshot-полей нет, используются данные каталога."""
        items_index = {
            102: {"name": "Каталожное имя", "sku": "CAT-SKU", "unit_symbol": "л"}
        }
        operation = {
            "id": "op3",
            "operation_type": "RECEIVE",
            "status": "draft",
            "site_id": 1,
            "lines": [
                {
                    "line_number": 1,
                    "item_id": 102,
                    "qty": "3.000",
                }
            ]
        }
        presented = self.service._present_operation(
            operation,
            items_index=items_index,
            sites_index={1: {"site_id": 1, "name": "Склад 1"}}
        )
        line = presented["lines"][0]
        self.assertEqual(line["item_name"], "Каталожное имя")
        self.assertEqual(line["sku"], "CAT-SKU")
        self.assertEqual(line["unit_symbol"], "л")
        self.assertFalse(line["is_temporary"])
