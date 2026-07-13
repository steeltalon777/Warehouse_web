from __future__ import annotations

import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.documents.models import RenderedDocumentArtifact
from apps.documents.services import (
    _estimated_line_units,
    _page_unit_capacity,
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

    def test_cache_key_contains_current_layout_namespace(self) -> None:
        """rev. 7 content-aware layout must not reuse v5/v6 cached PDFs."""
        from apps.documents.services import WAYBILL_LAYOUT_CACHE_VERSION, _cache_identity

        identity = _cache_identity(_document())
        cache_key = (
            f"waybill_pdf:{identity['document_id']}:{identity['payload_hash']}"
            f":{identity['renderer_version']}:{identity['template_version']}"
            f":{WAYBILL_LAYOUT_CACHE_VERSION}"
        )
        self.assertTrue(cache_key.endswith(":layout-v7"))

    # ------------------------------------------------------------------
    # TZ-V3.1I rev. 7 — content-aware physical-row pagination
    # ------------------------------------------------------------------

    def _assert_capacity_and_order(self, lines: list[dict], operation_type: str) -> None:
        pages = paginate_waybill_lines(lines, operation_type=operation_type)
        flattened = [line["line_number"] for page in pages for line in page["lines"]]
        self.assertEqual(flattened, [line["line_number"] for line in lines])
        for page in pages:
            layout = "single" if len(pages) == 1 else page["layout"]
            units = sum(_estimated_line_units(line) for line in page["lines"])
            self.assertLessEqual(units, _page_unit_capacity(layout=layout, operation_type=operation_type))

    def test_line_unit_estimator_handles_word_wrap_and_tokens(self) -> None:
        self.assertEqual(_estimated_line_units({"item_name": "Короткое имя"}), 1)
        self.assertGreaterEqual(
            _estimated_line_units({"item_name": "Наименование " * 8}), 2
        )
        self.assertGreaterEqual(_estimated_line_units({"item_name": "X" * 81}), 2)

    def test_capacity_invariants_preserve_order_for_all_signature_types(self) -> None:
        lines = _short_lines(60)
        lines[12]["item_name"] = "Длинное наименование запасной части для складского учёта"
        lines[21]["item_name"] = "Y" * 57
        for operation_type in ("RECEIVE", "ISSUE", "ISSUE_RETURN", "EXPENSE", "WRITE_OFF", "MOVE"):
            with self.subTest(operation_type=operation_type):
                self._assert_capacity_and_order(lines, operation_type)

    def test_regression_wrapped_22_lines_leave_room_for_last_signature(self) -> None:
        lines = _short_lines(22)
        lines[12]["item_name"] = "Насос центробежный многоступенчатый промышленный для чистой воды"
        lines[21]["item_name"] = "Комплект монтажный соединительный усиленный для трубопровода"
        pages = paginate_waybill_lines(lines, operation_type="MOVE")

        self.assertEqual(len(pages), 2)
        self.assertLess(len(pages[0]["lines"]), 22)
        self.assertEqual([line["line_number"] for page in pages for line in page["lines"]], list(range(1, 23)))
        self._assert_capacity_and_order(lines, "MOVE")

    def test_weasyprint_regression_pages_match_logical_pages(self) -> None:
        try:
            from weasyprint import HTML
        except ImportError:
            self.skipTest("WeasyPrint is unavailable in this Python environment")

        lines = _short_lines(22)
        lines[12]["item_name"] = "Насос центробежный многоступенчатый промышленный для чистой воды"
        lines[21]["item_name"] = "Комплект монтажный соединительный усиленный для трубопровода"
        document = _document(lines, operation_type="MOVE")
        context = build_waybill_context(document)
        rendered = HTML(string=render_document_html(document)).render()

        self.assertEqual(len(rendered.pages), len(context["pages"]))
        for page in rendered.pages:
            text = "".join(
                box.text for box in page._page_box.descendants() if getattr(box, "text", None)
            )
            self.assertIn("Кладовщик:", text)
            self.assertIn("ТМЦ", text, "PDF page must contain a table row, not only a signature/counter")

    def test_single_page_uses_full_last_signature_capacity(self) -> None:
        self.assertEqual(len(paginate_waybill_lines(_short_lines(16), operation_type="MOVE")), 2)
        self.assertEqual(len(paginate_waybill_lines(_short_lines(15), operation_type="MOVE")), 1)

    def test_pagination_empty(self) -> None:
        pages = paginate_waybill_lines([])
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["lines"], [])
        self.assertTrue(pages[0]["is_first"])
        self.assertTrue(pages[0]["is_last"])

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
        self.assertIn("overflow-wrap: anywhere", html)

    def test_waybill_html_signature_is_last_in_page(self) -> None:
        """План B: signature-block идёт ПОСЛЕ table внутри .page."""
        html = render_document_html(_document())
        # Найти позиции первого вхождения table и signature-block.
        table_pos = html.find("waybill-table")
        sig_pos = html.find("signature-block")
        self.assertGreater(table_pos, 0)
        self.assertGreater(sig_pos, table_pos)

    def test_content_aware_capacity_constants_keep_safety_reserve(self) -> None:
        self.assertEqual(_page_unit_capacity(layout="first", operation_type="MOVE"), 22)
        self.assertEqual(_page_unit_capacity(layout="middle", operation_type="MOVE"), 28)
        self.assertEqual(_page_unit_capacity(layout="last", operation_type="MOVE"), 19)
        self.assertEqual(_page_unit_capacity(layout="last", operation_type="ISSUE"), 25)
        self.assertEqual(_page_unit_capacity(layout="last", operation_type="RECEIVE"), 26)
