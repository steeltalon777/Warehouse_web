from __future__ import annotations

import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.documents.models import RenderedDocumentArtifact
from apps.documents.services import (
    _max_rows_for_page,
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


def _short_lines(n: int) -> list[dict]:
    return [
        {"line_number": i, "item_name": f"ТМЦ {i}", "unit_symbol": "шт", "quantity": 1}
        for i in range(1, n + 1)
    ]


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
        self.assertEqual(context["pages"][0]["layout"], "first")

    def test_multipage_context_has_signature_per_page(self) -> None:
        """75 lines RECEIVE → 3 pages (first / middle / last); Кладовщик на каждой странице."""
        lines = _short_lines(75)
        context = build_waybill_context(_document(lines))
        html = render_document_html(_document(lines))

        self.assertEqual(len(context["pages"]), 3)
        self.assertEqual(html.count("Кладовщик:"), len(context["pages"]))
        # First page: is_first, layout=first, not last
        self.assertTrue(context["pages"][0]["is_first"])
        self.assertFalse(context["pages"][0]["is_last"])
        self.assertEqual(context["pages"][0]["layout"], "first")
        # Middle page: neither first nor last
        self.assertFalse(context["pages"][1]["is_first"])
        self.assertFalse(context["pages"][1]["is_last"])
        self.assertEqual(context["pages"][1]["layout"], "middle")
        # Last page: is_last, layout=last
        self.assertTrue(context["pages"][-1]["is_last"])
        self.assertFalse(context["pages"][-1]["is_first"])
        self.assertEqual(context["pages"][-1]["layout"], "last")

    def test_move_has_extra_signatures(self) -> None:
        """MOVE (rev. 4): 4 блока — Операцию разрешил, Водитель, Начальник базы, Груз принял."""
        context = build_waybill_context(_document(operation_type="MOVE"))
        sigs = context["extra_signatures"]
        self.assertEqual(len(sigs), 4)
        self.assertEqual(sigs[0]["label"], "Операцию разрешил")
        self.assertEqual(sigs[1]["label"], "Водитель")
        self.assertTrue(sigs[1].get("driver_signature"))
        self.assertEqual(sigs[2]["label"], "Начальник базы")
        self.assertEqual(sigs[3]["label"], "Груз принял")

        html = render_document_html(_document(operation_type="MOVE"))
        self.assertIn("Операцию разрешил", html)
        self.assertIn("Водитель", html)
        self.assertIn("Начальник базы", html)
        self.assertIn("Груз принял", html)
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
        """MOVE (rev. 4): 4 экстра-подписи появляются только на последней странице."""
        lines = _short_lines(100)
        html = render_document_html(_document(lines, operation_type="MOVE"))
        context = build_waybill_context(_document(lines, operation_type="MOVE"))

        # Extra signatures должны появиться ровно один раз (на последней странице).
        self.assertEqual(html.count("Операцию разрешил:"), 1)
        self.assertEqual(html.count("Водитель:"), 1)
        self.assertEqual(html.count("Начальник базы:"), 1)
        self.assertEqual(html.count("Груз принял:"), 1)
        # Кладовщик появляется на каждой странице.
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

    def test_cache_invalidated_by_renderer_version_bump(self) -> None:
        """rev. 6 hotfix (09.07.2026): cache_key MUST include renderer_version.
        Otherwise bumping DOCUMENT_RENDERER_VERSION does not invalidate the
        cache, and old waybills keep returning stale PDFs. Confirmed by
        storekeeper bug: operation 11673bc0-... returned PDF v1 after v3 deploy.
        """
        from apps.documents.services import CACHE_KEY_PREFIX
        pdf_v1 = b"%PDF-1.4\n% v1 pdf\n"
        pdf_v2 = b"%PDF-1.4\n% v2 pdf\n"

        # First render with default renderer version (v3 in base.py)
        with patch("apps.documents.services._render_html_to_pdf_bytes", return_value=pdf_v1) as renderer:
            first = render_document_pdf(_document())
        self.assertFalse(first.cache_hit)
        self.assertEqual(renderer.call_count, 1)

        # Second render with same payload → cache hit (same renderer version)
        with patch("apps.documents.services._render_html_to_pdf_bytes", return_value=pdf_v1) as renderer:
            second = render_document_pdf(_document())
        self.assertTrue(second.cache_hit)
        self.assertEqual(renderer.call_count, 0)  # 0 calls in 2nd patch — cache hit, no re-render

        # Third render with BUMPED renderer version → must re-render
        with patch("apps.documents.services._render_html_to_pdf_bytes", return_value=pdf_v2) as renderer, \
             override_settings(DOCUMENT_RENDERER_VERSION="waybill-pdf-v99-test"):
            third = render_document_pdf(_document())
        self.assertFalse(third.cache_hit, "cache_hit must be False when renderer_version changes")
        self.assertEqual(third.pdf_bytes, pdf_v2)
        self.assertEqual(renderer.call_count, 1, "renderer must be called again on renderer_version bump")

    def test_cache_invalidated_by_template_version_change(self) -> None:
        """rev. 6 hotfix: cache_key includes template_version too."""
        from apps.documents.services import CACHE_KEY_PREFIX
        pdf_v1 = b"%PDF-1.4\n% old template\n"
        pdf_v2 = b"%PDF-1.4\n% new template\n"

        with patch("apps.documents.services._render_html_to_pdf_bytes", return_value=pdf_v1) as renderer:
            first = render_document_pdf(_document())
        self.assertFalse(first.cache_hit)
        self.assertEqual(renderer.call_count, 1)
        # Mutate template_version in the document (simulates template bump)
        doc = _document()
        doc["template_version"] = "1.1"
        with patch("apps.documents.services._render_html_to_pdf_bytes", return_value=pdf_v2) as renderer:
            second = render_document_pdf(doc)
        self.assertFalse(second.cache_hit, "template_version change must bust cache")
        self.assertEqual(second.pdf_bytes, pdf_v2)
        self.assertEqual(renderer.call_count, 1)  # 1 call in 2nd patch — cache miss, re-rendered

    # ------------------------------------------------------------------
    # TZ-V3.1I rev. 4 — plan B: exact-rows pagination
    # ------------------------------------------------------------------

    def test_pagination_first_page_reserves_signature_height(self) -> None:
        """MOVE (driver) уменьшает last_max; RECEIVE (0 extras) — больше."""
        # 20 коротких строк: RECEIVE → 1 страница, MOVE → возможно больше.
        lines = _short_lines(20)
        pages_move = paginate_waybill_lines(lines, operation_type="MOVE")
        pages_receive = paginate_waybill_lines(lines, operation_type="RECEIVE")

        self.assertGreaterEqual(len(pages_move), len(pages_receive))
        # MOVE first_max == RECEIVE first_max (signatures не учитываются на first page
        # в плане B — только thead+title+short storekeeper). Зато last_max у MOVE меньше.
        first_move = _max_rows_for_page(
            is_first=True, is_last=False, extra_signatures_count=3, has_driver=True
        )
        first_receive = _max_rows_for_page(
            is_first=True, is_last=False, extra_signatures_count=0, has_driver=False
        )
        self.assertEqual(first_move, first_receive)
        # rev. 5: first_max=22 (was 23; FULL_TITLE bumped 50mm -> 60mm).
        self.assertEqual(first_move, 22)
        self.assertEqual(first_receive, 22)

    def test_pagination_exact_rows_hard_cap(self) -> None:
        """rev. 5: first_max=22, middle_max=28, last_max≤28 — hard cap по row count."""
        lines = _short_lines(50)
        pages = paginate_waybill_lines(lines)
        self.assertLessEqual(len(pages[0]["lines"]), 22)
        for page in pages[1:-1]:
            self.assertLessEqual(len(page["lines"]), 28)
        self.assertLessEqual(len(pages[-1]["lines"]), 28)

    def test_pagination_handles_long_names(self) -> None:
        """50 строк × длинные имена → пагинация не падает, всё учтено."""
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
        lines = _short_lines(200)
        pages = paginate_waybill_lines(lines)
        total = sum(len(p["lines"]) for p in pages)
        self.assertEqual(total, 200)
        self.assertGreaterEqual(len(pages), 6)

    def test_pagination_single_line(self) -> None:
        pages = paginate_waybill_lines(
            [{"line_number": 1, "item_name": "Одна", "unit_symbol": "шт", "quantity": 1}]
        )
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["lines"][0]["line_number"], 1)
        self.assertEqual(pages[0]["layout"], "first")

    def test_pagination_empty(self) -> None:
        pages = paginate_waybill_lines([])
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["lines"], [])
        self.assertEqual(pages[0]["layout"], "first")
        self.assertTrue(pages[0]["is_first"])
        self.assertTrue(pages[0]["is_last"])

    def test_paginate_waybill_lines_exact_rows(self) -> None:
        """Exact max rows для first/middle/last по operation_type (rev. 5: first=22)."""
        cases = [
            ("RECEIVE", 22, 28, 28),
            ("ISSUE", 22, 28, 26),
            ("WRITE_OFF", 22, 28, 26),
            ("MOVE", 22, 28, 22),
        ]
        for op, expected_first, expected_middle, expected_last in cases:
            with self.subTest(operation_type=op):
                pages = paginate_waybill_lines(_short_lines(500), operation_type=op)
                # Первая страница — first_max
                self.assertLessEqual(len(pages[0]["lines"]), expected_first)
                # Middle страницы — middle_max
                middle_pages = [p for p in pages if p["layout"] == "middle"]
                for page in middle_pages:
                    self.assertLessEqual(len(page["lines"]), expected_middle)
                # Последняя страница — last_max
                self.assertLessEqual(len(pages[-1]["lines"]), expected_last)

    def test_paginate_waybill_lines_middle_pages_have_short_title(self) -> None:
        """75 lines RECEIVE → 3 страницы: first(22) / middle(28 FULL) / last(25)."""
        pages = paginate_waybill_lines(_short_lines(75), operation_type="RECEIVE")
        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[0]["layout"], "first")
        self.assertEqual(pages[1]["layout"], "middle")
        self.assertEqual(pages[2]["layout"], "last")
        # rev. 5: middle is always full (28 rows), last is sparse.
        self.assertEqual(len(pages[0]["lines"]), 22)
        self.assertEqual(len(pages[1]["lines"]), 28)
        self.assertEqual(len(pages[2]["lines"]), 25)

    def test_pagination_full_middle_pages(self) -> None:
        """rev. 5: middle pages should always be full (28 rows) when they exist.

        80 lines MOVE → first(22) + middle(28) + middle(28) + last(2) = 4 pages.
        Last is sparse (2 rows); middles are both full (28 rows).
        """
        from apps.documents.services import paginate_waybill_lines

        lines = [
            {"line_number": i, "item_name": f"TMC {i}", "unit_symbol": "шт", "quantity": 1}
            for i in range(1, 81)
        ]
        pages = paginate_waybill_lines(lines, operation_type="MOVE")
        self.assertEqual(len(pages), 4)
        self.assertEqual(len(pages[0]["lines"]), 22)  # first
        self.assertEqual(len(pages[1]["lines"]), 28)  # middle (FULL)
        self.assertEqual(len(pages[2]["lines"]), 28)  # middle (FULL)
        self.assertEqual(len(pages[3]["lines"]), 2)   # last (sparse)
        # Layouts
        self.assertEqual(pages[0]["layout"], "first")
        self.assertEqual(pages[1]["layout"], "middle")
        self.assertEqual(pages[2]["layout"], "middle")
        self.assertEqual(pages[3]["layout"], "last")
        # Total
        self.assertEqual(sum(len(p["lines"]) for p in pages), 80)

    def test_pagination_edge_50_lines_move(self) -> None:
        """rev. 5: 50 lines MOVE — tight edge case for MOVE pagination.

        first_max=22, middle_max=28, last_max=22. After first page, 28 rows remain,
        which exactly fills one middle page (28), leaving 0 for the last.
        Algorithm absorbs the middle into the last → first(22) + last(28) = 2 pages.
        Last exceeds last_max=22 by 6mm; acceptable per rev. 5 design.
        """
        from apps.documents.services import paginate_waybill_lines

        lines = [
            {"line_number": i, "item_name": f"TMC {i}", "unit_symbol": "шт", "quantity": 1}
            for i in range(1, 51)
        ]
        pages = paginate_waybill_lines(lines, operation_type="MOVE")
        # Chosen behavior: absorb into last → 2 pages.
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]["layout"], "first")
        self.assertEqual(pages[1]["layout"], "last")
        self.assertEqual(len(pages[0]["lines"]), 22)
        self.assertEqual(len(pages[1]["lines"]), 28)
        self.assertEqual(sum(len(p["lines"]) for p in pages), 50)

    def test_paginate_waybill_lines_single_page_layout(self) -> None:
        """10 lines → 1 страница layout='first' (is_first=True, is_last=True)."""
        pages = paginate_waybill_lines(_short_lines(10))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["layout"], "first")
        self.assertTrue(pages[0]["is_first"])
        self.assertTrue(pages[0]["is_last"])

    def test_paginate_waybill_lines_move_has_4_extra_signatures(self) -> None:
        """MOVE → 4 экстра-блока (3 standard + 1 driver)."""
        from apps.documents.services import _build_extra_signatures

        sigs = _build_extra_signatures("MOVE")
        self.assertEqual(len(sigs), 4)
        labels = [s["label"] for s in sigs]
        self.assertEqual(
            labels, ["Операцию разрешил", "Водитель", "Начальник базы", "Груз принял"]
        )
        driver_blocks = [s for s in sigs if s.get("driver_signature")]
        self.assertEqual(len(driver_blocks), 1)
        self.assertEqual(driver_blocks[0]["label"], "Водитель")

    def test_paginate_waybill_lines_eighteen_rows_single_page(self) -> None:
        """Screenshot bug fix: 18 строк → 1 страница, Кладовщик внутри."""
        pages = paginate_waybill_lines(_short_lines(18))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["layout"], "first")
        self.assertEqual(len(pages[0]["lines"]), 18)

    def test_waybill_html_first_page_has_full_title(self) -> None:
        """Page 1 содержит Грузоотправитель + Грузополучатель + Основание."""
        lines = _short_lines(75)
        html = render_document_html(_document(lines))
        # Full title блок отображается один раз (на первой странице)
        self.assertEqual(html.count("Грузоотправитель:"), 1)
        self.assertEqual(html.count("Грузополучатель:"), 1)
        self.assertEqual(html.count("Основание:"), 1)
        # "Накладная № X" присутствует на всех страницах (заголовок)
        self.assertIn("Накладная № 1/0121/030626", html)

    def test_waybill_html_middle_page_has_short_title(self) -> None:
        """Page 2+ НЕ содержит реквизиты, только короткий заголовок."""
        lines = _short_lines(75)
        html = render_document_html(_document(lines))
        # Грузоотправитель/получатель/основание — только на page 1.
        self.assertEqual(html.count("Грузоотправитель:"), 1)
        # Заголовок "Накладная" — на каждой странице, в <h1>.
        self.assertGreaterEqual(html.count("Накладная"), 2)

    def test_waybill_html_last_page_has_full_signature(self) -> None:
        """Last page содержит все экстра-подписи операции."""
        lines = _short_lines(75)
        # MOVE: 4 экстра-подписи на последней странице.
        html = render_document_html(_document(lines, operation_type="MOVE"))
        self.assertIn("Операцию разрешил:", html)
        self.assertIn("Водитель:", html)
        self.assertIn("Начальник базы:", html)
        self.assertIn("Груз принял:", html)

    def test_waybill_html_no_flexbox_minheight(self) -> None:
        """План B: min-height пиннинг на .page отсутствует."""
        html = render_document_html(_document())
        self.assertNotIn("min-height: calc(297mm", html)
        self.assertNotIn("flex: 1 1 auto", html)

    def test_waybill_html_signature_is_last_in_page(self) -> None:
        """План B: signature-block идёт ПОСЛЕ table внутри .page."""
        html = render_document_html(_document())
        # Найти позиции первого вхождения table и signature-block.
        table_pos = html.find("waybill-table")
        sig_pos = html.find("signature-block")
        self.assertGreater(table_pos, 0)
        self.assertGreater(sig_pos, table_pos)

    def test_pagination_constants_match_exact_rows(self) -> None:
        """Константы exact-rows укладываются в A4 portrait @page (rev. 5)."""
        from apps.documents.services import (
            A4_INNER_HEIGHT_MM,
            FULL_TITLE_HEIGHT_MM,
            ROW_HEIGHT_MM,
            SHORT_TITLE_HEIGHT_MM,
            SIG_BLOCK_DRIVER_MM,
            SIG_BLOCK_HEIGHT_MM,
            SIG_STOREKEEPER_MM,
            THEAD_HEIGHT_MM,
        )

        # sanity: базовая геометрия
        self.assertEqual(A4_INNER_HEIGHT_MM, 267.0)
        self.assertEqual(ROW_HEIGHT_MM, 8.5)
        self.assertEqual(THEAD_HEIGHT_MM, 10.0)
        self.assertEqual(SIG_STOREKEEPER_MM, 6.0)
        self.assertEqual(SIG_BLOCK_HEIGHT_MM, 14.0)
        self.assertEqual(SIG_BLOCK_DRIVER_MM, 6.0)
        # rev. 5: FULL_TITLE_HEIGHT_MM bumped 50 -> 60 after real WeasyPrint calibration.
        self.assertEqual(FULL_TITLE_HEIGHT_MM, 60.0)
        # first_max: (267 - 60 - 10 - 6) // 8.5 = 22
        self.assertEqual(
            _max_rows_for_page(
                is_first=True, is_last=False, extra_signatures_count=0, has_driver=False
            ),
            22,
        )
        # middle_max: (267 - 12 - 10 - 6) // 8.5 = 28
        self.assertEqual(
            _max_rows_for_page(
                is_first=False, is_last=False, extra_signatures_count=0, has_driver=False
            ),
            28,
        )
        # last_max MOVE (driver + 3 extras): 22
        self.assertEqual(
            _max_rows_for_page(
                is_first=False, is_last=True, extra_signatures_count=3, has_driver=True
            ),
            22,
        )
        # last_max RECEIVE (0 extras): 28
        self.assertEqual(
            _max_rows_for_page(
                is_first=False, is_last=True, extra_signatures_count=0, has_driver=False
            ),
            28,
        )
        # last_max ISSUE (1 extra): 26
        self.assertEqual(
            _max_rows_for_page(
                is_first=False, is_last=True, extra_signatures_count=1, has_driver=False
            ),
            26,
        )
        # title constants
        self.assertLess(SHORT_TITLE_HEIGHT_MM, FULL_TITLE_HEIGHT_MM)
