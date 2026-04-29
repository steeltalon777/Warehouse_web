from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from apps.balances.views import _get_default_balance_site_id, _present_balance_row


class BalanceViewHelpersTests(SimpleTestCase):
    def test_storekeeper_defaults_to_own_site(self) -> None:
        request = RequestFactory().get("/balances/")
        request.session = {"sync_role": "storekeeper", "sync_default_site_id": "7"}
        request.user = SimpleNamespace(is_authenticated=True)

        self.assertEqual(_get_default_balance_site_id(request), "7")

    def test_global_roles_default_to_all_sites(self) -> None:
        for role in ("observer", "chief_storekeeper", "root"):
            request = RequestFactory().get("/balances/")
            request.session = {"sync_role": role, "sync_default_site_id": "7"}
            request.user = SimpleNamespace(is_authenticated=True)

            self.assertEqual(_get_default_balance_site_id(request), "")

    def test_present_balance_row_prefers_api_item_fields(self) -> None:
        row = {
            "site_id": 2,
            "display_name": "Кабель силовой",
            "sku": "CBL-001",
            "category_name": "Кабели",
            "qty": "12",
        }

        presented = _present_balance_row(
            row,
            sites_index={2: {"site_id": 2, "name": "Основной склад"}},
            items_index={},
        )

        self.assertEqual(presented["item_name"], "Кабель силовой")
        self.assertEqual(presented["sku"], "CBL-001")
        self.assertEqual(presented["category_name"], "Кабели")
        self.assertEqual(presented["site_name"], "Основной склад")
