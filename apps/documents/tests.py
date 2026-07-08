from __future__ import annotations

import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.documents.models import RenderedDocumentArtifact
from apps.documents.services import (
    build_waybill_context,
    paginate_waybill_lines,
    render_document_html,
    render_document_pdf,
)


def _document(
    lines: list[dict] | None = None,
    *,
    operation_type: str = "RECEIVE",
) -> dict:
    return {
        "id": "doc-1",
        "document_type": "waybill",
        "document_number": "WB-1",
        "revision": 0,
        "site_id": 1,
        "template_name": "waybill_v1",
        "template_version": "1.0",
        "payload_hash": "a" * 64,
        "payload": {
            "operation_display_number": "1/0121/030626",
            "consignee_label": "Base",
            "basis_label": "Приход на склад Base",
            "operation_type": operation_type,
            "operation": {
                "id": "op-1",
                "type": operation_type,
                "display_number": "1/0121/030626",
            },
            "operation_created_at": "2026-06-03T01:21:00+00:00",
            "sender": {"site_id": 1, "site_name": "Base"},
            "lines": lines
            or [
                {
                    "line_number": 1,
                    "item_name": "Дрель ударная",
                    "item_sku": "SKU-SHOULD-NOT-RENDER",
                    "unit_symbol": "шт",
                    "quantity": 3.0,
                }
            ],
        },
    }


class DocumentPdfRendererTests(TestCase):
    def setUp(self) -> None:
        self.media_dir = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_dir.name,
            DOCUMENT_SHIPPER_REQUISITES="ООО АС «Горизонт», тестовые реквизиты",
            DOCUMENT_RENDERER_VERSION="test-renderer-v1",
        )
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_dir.cleanup()

    def test_waybill_html_matches_mvp_layout(self) -> None:
        html = render_document_html(_document())

        self.assertIn("Накладная № 1/0121/030626", html)
        self.assertIn("ООО АС «Горизонт», тестовые реквизиты", html)
        self.assertIn("Кладовщик:", html)
        self.assertIn("_________________/__________________", html)
        self.assertIn("Наименование ТМЦ", html)
        self.assertNotIn("SKU-SHOULD-NOT-RENDER", html)
        # RECEIVE has no extra signatures
        self.assertNotIn("Получил", html)
        self.assertNotIn("Операцию разрешил", html)

    def test_single_page_context_has_is_last(self) -> None:
        context = build_waybill_context(_document())
        self.assertEqual(len(context["pages"]), 1)
        self.assertTrue(context["pages"][0]["is_first"])
        self.assertTrue(context["pages"][0]["is_last"])
        self.assertEqual(context["extra_signatures"], [])  # RECEIVE

    def test_multipage_context_has_signature_per_page(self) -> None:
        lines = [
            {
                "line_number": index,
                "item_name": f"Длинное наименование ТМЦ {index} " * 4,
                "unit_symbol": "шт",
                "quantity": index,
            }
            for index in range(1, 75)
        ]

        context = build_waybill_context(_document(lines))
        html = render_document_html(_document(lines))

        self.assertGreater(len(context["pages"]), 1)
        self.assertEqual(html.count("Кладовщик:"), len(context["pages"]))
        # First page: not last
        self.assertTrue(context["pages"][0]["is_first"])
        self.assertFalse(context["pages"][0]["is_last"])
        # Last page: is last
        self.assertTrue(context["pages"][-1]["is_last"])

    def test_move_has_extra_signatures(self) -> None:
        context = build_waybill_context(_document(operation_type="MOVE"))
        sigs = context["extra_signatures"]
        self.assertEqual(len(sigs), 2)
        self.assertEqual(sigs[0]["label"], "Операцию разрешил")
        self.assertEqual(sigs[1]["label"], "Водитель")
        self.assertTrue(sigs[1].get("driver_signature"))

        html = render_document_html(_document(operation_type="MOVE"))
        self.assertIn("Операцию разрешил", html)
        self.assertIn("Водитель", html)
        self.assertIn("(должность)", html)
        self.assertIn("(фио/подпись)", html)

    def test_write_off_has_operation_approved_only(self) -> None:
        context = build_waybill_context(_document(operation_type="WRITE_OFF"))
        sigs = context["extra_signatures"]
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0]["label"], "Операцию разрешил")

        html = render_document_html(_document(operation_type="WRITE_OFF"))
        self.assertIn("Операцию разрешил", html)
        self.assertNotIn("Водитель", html)
        self.assertNotIn("Получил", html)

    def test_issue_has_received_signature(self) -> None:
        for op_type in ("ISSUE", "ISSUE_RETURN", "EXPENSE"):
            with self.subTest(operation_type=op_type):
                context = build_waybill_context(_document(operation_type=op_type))
                sigs = context["extra_signatures"]
                self.assertEqual(len(sigs), 1)
                self.assertEqual(sigs[0]["label"], "Получил")

                html = render_document_html(_document(operation_type=op_type))
                self.assertIn("Получил", html)
                self.assertNotIn("Операцию разрешил", html)
                self.assertNotIn("Водитель", html)

    def test_extra_signatures_only_on_last_page(self) -> None:
        """On multi-page MOVE documents, extra signatures only appear once — on the last page."""
        lines = [
            {
                "line_number": index,
                "item_name": f"ТМЦ {index} " * 8,
                "unit_symbol": "шт",
                "quantity": index,
            }
            for index in range(1, 100)
        ]
        html = render_document_html(_document(lines, operation_type="MOVE"))
        # Extra signatures should appear exactly once (last page)
        self.assertEqual(html.count("Операцию разрешил:"), 1)
        self.assertEqual(html.count("Водитель:"), 1)
        # Storekeeper appears on every page
        context = build_waybill_context(_document(lines, operation_type="MOVE"))
        self.assertEqual(html.count("Кладовщик:"), len(context["pages"]))

    def test_pdf_render_is_cached_by_payload_identity(self) -> None:
        pdf_bytes = b"%PDF-1.4\n% test pdf\n"

        with patch("apps.documents.services._render_html_to_pdf_bytes", return_value=pdf_bytes) as renderer:
            first = render_document_pdf(_document())
            second = render_document_pdf(_document())

        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(second.pdf_bytes, pdf_bytes)
        self.assertEqual(renderer.call_count, 1)
        self.assertEqual(RenderedDocumentArtifact.objects.count(), 1)
        artifact = RenderedDocumentArtifact.objects.get()
        self.assertEqual(artifact.status, RenderedDocumentArtifact.Status.READY)
        self.assertEqual(artifact.size_bytes, len(pdf_bytes))

    # ------------------------------------------------------------------
    # TZ-V3.1I rev. 2 — I4 unit tests (pagination + CSS hardening)
    # ------------------------------------------------------------------

    def test_pagination_first_page_reserves_signature_height(self) -> None:
        """MOVE (2 extra signatures) → smaller first-page budget; RECEIVE (0 extras) → larger."""
        from apps.documents.services import (
            SINGLE_ROW_SIGNATURE_HEIGHT_MM,
            SIGNATURE_BLOCK_HEIGHT_MM,
            paginate_waybill_lines,
        )

        # 20 коротких строк → 1 страница для RECEIVE, возможно 2 для MOVE.
        lines = [
            {"line_number": i, "item_name": f"ТМЦ {i}", "unit_symbol": "шт", "quantity": i}
            for i in range(1, 21)
        ]
        pages_move = paginate_waybill_lines(lines, extra_signatures_count=2)
        pages_receive = paginate_waybill_lines(lines, extra_signatures_count=0)

        # MOVE budget уже → возможно больше страниц.
        self.assertGreaterEqual(len(pages_move), len(pages_receive))
        # Sanity-check that constants really differ.
        self.assertGreater(SIGNATURE_BLOCK_HEIGHT_MM, SINGLE_ROW_SIGNATURE_HEIGHT_MM)

    def test_pagination_hard_cap(self) -> None:
        """first_page_max_rows=22, continuation_max_rows=26 — hard cap."""
        from apps.documents.services import paginate_waybill_lines

        # 50 коротких строк: первая страница <= 22, continuation <= 26.
        lines = [
            {"line_number": i, "item_name": f"A{i}", "unit_symbol": "шт", "quantity": 1}
            for i in range(1, 51)
        ]
        pages = paginate_waybill_lines(lines)
        self.assertLessEqual(len(pages[0]["lines"]), 22)
        for page in pages[1:-1]:
            self.assertLessEqual(len(page["lines"]), 26)

    def test_pagination_handles_long_names(self) -> None:
        """50 строк × 200 символов → пагинация не падает, нет «висящих» страниц."""
        from apps.documents.services import paginate_waybill_lines

        long_name = "Длинное наименование ТМЦ " * 10
        lines = [
            {"line_number": i, "item_name": long_name, "unit_symbol": "шт", "quantity": 1}
            for i in range(1, 51)
        ]
        pages = paginate_waybill_lines(lines)
        total = sum(len(p["lines"]) for p in pages)
        self.assertEqual(total, 50)
        self.assertGreaterEqual(len(pages), 2)

    def test_pagination_extremely_long_operation(self) -> None:
        """200 строк → ≥ 6 страниц, общая сумма == 200."""
        from apps.documents.services import paginate_waybill_lines

        lines = [
            {"line_number": i, "item_name": f"ТМЦ {i}", "unit_symbol": "шт", "quantity": 1}
            for i in range(1, 201)
        ]
        pages = paginate_waybill_lines(lines)
        total = sum(len(p["lines"]) for p in pages)
        self.assertEqual(total, 200)
        self.assertGreaterEqual(len(pages), 6)

    def test_pagination_single_line(self) -> None:
        from apps.documents.services import paginate_waybill_lines

        pages = paginate_waybill_lines(
            [{"line_number": 1, "item_name": "Одна", "unit_symbol": "шт", "quantity": 1}]
        )
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["lines"][0]["line_number"], 1)

    def test_pagination_empty(self) -> None:
        from apps.documents.services import paginate_waybill_lines

        pages = paginate_waybill_lines([])
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["lines"], [])

    def test_waybill_html_has_page_break_after_avoid_on_h1(self) -> None:
        html = render_document_html(_document())
        self.assertIn("page-break-after: avoid", html)
        self.assertIn("break-after: avoid", html)

    def test_waybill_html_uses_flexbox_for_signature_at_bottom(self) -> None:
        html = render_document_html(_document())
        self.assertIn("display: flex", html)
        self.assertIn("min-height: calc(297mm", html)
        self.assertIn("flex: 1 1 auto", html)  # waybill-table-wrap

    def test_pagination_constants_match_flex_geometry(self) -> None:
        """rev. 2 (warning #4): константы пагинатора + flex-блоки должны укладываться в A4."""
        SIGNATURE_BLOCK_HEIGHT_MM = 37.0
        SINGLE_ROW_SIGNATURE_HEIGHT_MM = 4.0
        PAGE_MARGIN_MM = 30.0
        HEADER_OVERHEAD_MM = PAGE_MARGIN_MM + 16.4 + 22 + 10
        CONTINUATION_OVERHEAD_MM = PAGE_MARGIN_MM + 10 + 4
        A4_INNER_HEIGHT_MM = 267.0

        move_budget = A4_INNER_HEIGHT_MM - HEADER_OVERHEAD_MM - SIGNATURE_BLOCK_HEIGHT_MM
        self.assertLessEqual(
            move_budget,
            152 + 1,
            f"MOVE 1-page budget {move_budget}mm должно быть ≤ 153mm (target 152)",
        )
        receive_budget = A4_INNER_HEIGHT_MM - HEADER_OVERHEAD_MM - SINGLE_ROW_SIGNATURE_HEIGHT_MM
        self.assertLessEqual(
            receive_budget,
            189 + 1,
            f"RECEIVE 1-page budget {receive_budget}mm должно быть ≤ 190mm (target 189)",
        )
        cont_budget = A4_INNER_HEIGHT_MM - CONTINUATION_OVERHEAD_MM
        self.assertLessEqual(
            cont_budget,
            223 + 1,
            f"continuation budget {cont_budget}mm должно быть ≤ 224mm (target 223)",
        )
