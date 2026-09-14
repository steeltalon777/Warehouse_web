"""Unit tests for the Phase 6D evidence collector command.

Covers corpus fetch/pagination, guards, uniform row schema, content checks
(text extraction, quantity normalization, loss/duplication, totals, empty
pages), summary distributions and the version/run manifest.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from apps.documents.management.commands.collect_phase6d_evidence import (
    MIN_SMALL_CORPUS_GUARD,
    RESULT_FIELDS,
    Command,
    _blank_result,
    _build_summary,
    _check_required_values,
    _classify_row,
    _compact_text,
    _count_numeric_occurrences,
    _extract_required_text,
    _git_info,
    _load_document_ids,
    _normalize_text,
    _quantity_variants,
    _read_git_sha_from_files,
)

COMMAND_MODULE = "apps.documents.management.commands.collect_phase6d_evidence"

TEMPLATE_MAP_220 = {"waybill": ("warehouse-waybill-ru", "2.2.0")}


def _fake_document(doc_id: str = "doc-1", *, item_name: str = "Ложка чайная", quantity: float = 1.0) -> dict:
    return {
        "id": doc_id,
        "document_type": "waybill",
        "document_number": f"WB-{doc_id}",
        "revision": 0,
        "payload_hash": "a" * 64,
        "payload": {
            "operation_display_number": "010126/0001/1",
            "operation": {"display_number": "010126/0001/1"},
            "lines": [{"item_name": item_name, "quantity": quantity, "unit_symbol": "шт"}],
        },
    }


def _expected_axes() -> dict:
    return {
        "template_id": "warehouse-waybill-ru",
        "template_version": "2.2.0",
        "document_contract": "warehouse.operation-document/v2",
        "engine": "qde",
        "engine_version": "1.0.0",
        "backend": "typst",
        "backend_version": "0.15.1",
    }


def _summary_corpus() -> dict:
    return {
        "source": "SyncServer GET /documents?document_type=waybill",
        "document_type": "waybill",
        "total_available": 3,
        "fetched": 3,
        "processed": 3,
        "pages_fetched": 1,
        "limit_applied": 0,
    }


class QuantityVariantTests(SimpleTestCase):
    def test_integral_decimals_are_normalized(self) -> None:
        variants = _quantity_variants("1.0")
        self.assertIn("1", variants)
        self.assertIn("1.0", variants)
        self.assertIn("1,0", variants)

    def test_fractional_values_keep_decimal_forms(self) -> None:
        variants = _quantity_variants("12.50")
        self.assertIn("12.5", variants)
        self.assertIn("12,5", variants)

    def test_non_numeric_values_pass_through(self) -> None:
        self.assertEqual(_quantity_variants("компл"), ["компл"])


class NumericOccurrenceTests(SimpleTestCase):
    def test_digit_boundaries_prevent_partial_matches(self) -> None:
        self.assertEqual(_count_numeric_occurrences("10 1 21", "1"), 1)
        self.assertEqual(_count_numeric_occurrences("10 21", "1"), 0)
        self.assertEqual(_count_numeric_occurrences("шт 1", "1"), 1)
        self.assertEqual(_count_numeric_occurrences("значение 1,0", "1,0"), 1)


class CompactTextTests(SimpleTestCase):
    def test_compact_removes_all_whitespace(self) -> None:
        self.assertEqual(_compact_text("а\u00a0б в\nг"), "абвг")


class GitInfoTests(SimpleTestCase):
    def test_filesystem_fallback_reads_head_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".git", "refs", "heads"))
            with open(os.path.join(tmp, ".git", "HEAD"), "w", encoding="utf-8") as handle:
                handle.write("ref: refs/heads/dev\n")
            with open(os.path.join(tmp, ".git", "refs", "heads", "dev"), "w", encoding="utf-8") as handle:
                handle.write("abc123\n")
            with (
                override_settings(BASE_DIR=tmp),
                patch(f"{COMMAND_MODULE}.subprocess.run", side_effect=FileNotFoundError("git")),
            ):
                info = _git_info()
        self.assertEqual(info["git_sha"], "abc123")
        self.assertEqual(info["git_branch"], "dev")
        self.assertEqual(info["git_source"], "filesystem")
        self.assertIsNone(info["git_dirty"])

    def test_filesystem_fallback_reads_packed_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".git"))
            with open(os.path.join(tmp, ".git", "HEAD"), "w", encoding="utf-8") as handle:
                handle.write("ref: refs/heads/main\n")
            with open(os.path.join(tmp, ".git", "packed-refs"), "w", encoding="utf-8") as handle:
                handle.write("# pack-refs with: peeled\n1111111111 refs/heads/main\n")
            sha, branch = _read_git_sha_from_files(tmp)
        self.assertEqual(sha, "1111111111")
        self.assertEqual(branch, "main")


class RequiredTextTests(SimpleTestCase):
    def test_extract_required_text_reads_canonical_contract(self) -> None:
        required = _extract_required_text(_fake_document("d1"))
        self.assertEqual(required["operation_display_number"], "010126/0001/1")
        self.assertEqual(required["item_names"], "Ложка чайная")
        self.assertEqual(required["quantities"], "1.0")
        self.assertEqual(required["lines"][0]["unit"], "шт")

    def test_normalize_text_collapses_nbsp_and_whitespace(self) -> None:
        self.assertEqual(_normalize_text("а\u00a0б\n в"), "а б в")


class ContentCheckTests(SimpleTestCase):
    def test_match_when_all_required_values_present(self) -> None:
        document = _fake_document("d1")
        text = "Накладная № 010126/0001/1 Ложка чайная шт 1 Итого 1"
        content = _check_required_values(document, text, text)
        self.assertEqual(content["value_losses"], [])
        self.assertEqual(content["unverified"], [])
        self.assertEqual(content["item_loss_count"], 0)
        self.assertFalse(content["totals_missing"])

    def test_item_loss_and_totals_detected(self) -> None:
        document = _fake_document("d1")
        legacy = "010126/0001/1 Ложка чайная шт 1 Итого 1"
        qde = "010126/0001/1"
        content = _check_required_values(document, legacy, qde)
        self.assertEqual(content["item_loss_count"], 1)
        self.assertIn("item:Ложка чайная", content["value_losses"])
        self.assertTrue(content["totals_missing"])

    def test_duplication_detected(self) -> None:
        document = _fake_document("d1")
        legacy = "010126/0001/1 Ложка чайная шт 1"
        qde = "010126/0001/1 Ложка чайная шт 1 Ложка чайная шт 1"
        content = _check_required_values(document, legacy, qde)
        self.assertEqual(content["item_duplication_count"], 1)

    def test_quantity_count_shortage_is_a_loss(self) -> None:
        document = _fake_document("d1")
        legacy = "010126/0001/1 Ложка чайная шт 1"
        qde = "010126/0001/1 Ложка чайная шт 2"
        content = _check_required_values(document, legacy, qde)
        self.assertIn("quantity:1.0", content["value_losses"])

    def test_quantity_anchor_ignores_page_counters(self) -> None:
        document = _fake_document("d1", quantity=2.0)
        legacy = "Лист 1 из 2 Ложка чайная шт 2 Лист 2 из 2"
        qde = "Лист 2 из 3 Ложка чайная шт 2 Лист 3 из 3"
        content = _check_required_values(document, legacy, qde)
        self.assertEqual(content["value_losses"], [])

    def test_negative_quantity_accepts_unicode_minus(self) -> None:
        document = _fake_document("d1", quantity=-2.0)
        legacy = "010126/0001/1 Ложка чайная шт -2"
        qde = "010126/0001/1 Ложка чайная шт \u22122"
        content = _check_required_values(document, legacy, qde)
        self.assertEqual(content["value_losses"], [])

    def test_short_unit_does_not_match_word_tail(self) -> None:
        document = _fake_document("d1", item_name="Рычаг")
        document["payload"]["lines"][0]["unit_symbol"] = "т"
        legacy = "010126/0001/1 Рычаг т 2 агрегат 2"
        qde = "010126/0001/1 Рычаг т 2"
        content = _check_required_values(document, legacy, qde)
        self.assertEqual(content["value_losses"], [])

    def test_display_number_not_fabricated_from_internal_number(self) -> None:
        document = {
            "id": "d1",
            "document_type": "waybill",
            "document_number": "WB-INTERNAL-1",
            "revision": 0,
            "payload_hash": "a" * 64,
            "payload": {"lines": [{"item_name": "Ложка чайная", "quantity": 1.0, "unit_symbol": "шт"}]},
        }
        required = _extract_required_text(document)
        self.assertIsNone(required["operation_display_number"])
        content = _check_required_values(document, "WB-INTERNAL-1 Ложка чайная шт 1", "WB-INTERNAL-1 Ложка чайная шт 1")
        self.assertEqual(content["value_losses"], [])
        self.assertEqual(content["unverified"], [])

    def test_unverified_when_value_absent_in_both_pdfs(self) -> None:
        document = _fake_document("d1", item_name="Шайба")
        text = "010126/0001/1"
        content = _check_required_values(document, text, text)
        self.assertIn("item:Шайба", content["unverified"])
        self.assertEqual(content["item_loss_count"], 0)

    def test_wrapped_hyphenated_name_is_matched(self) -> None:
        document = _fake_document("d1", item_name="Кружка гусь-хрустальный")
        text = "010126/0001/1 Кружка гусь-\nхрустальный шт 1"
        content = _check_required_values(document, text, text)
        self.assertEqual(content["value_losses"], [])
        self.assertEqual(content["unverified"], [])
        self.assertEqual(content["item_duplication_count"], 0)

    def test_wrapped_slash_name_is_matched(self) -> None:
        document = _fake_document("d1", item_name="Ремкомплект 401107-00323/A, K9002003")
        legacy = "010126/0001/1 Ремкомплект 401107-00323/A, K9002003 шт 1"
        qde = "010126/0001/1 Ремкомплект 401107-00323/\nA, K9002003 шт 1"
        content = _check_required_values(document, legacy, qde)
        self.assertEqual(content["value_losses"], [])
        self.assertEqual(content["unverified"], [])
        self.assertEqual(content["item_duplication_count"], 0)

    def test_wrapped_display_number_is_matched(self) -> None:
        document = _fake_document("d1")
        legacy = "010126/0001/1 Ложка чайная шт 1"
        qde = "010126/0001/\n1 Ложка чайная шт 1"
        content = _check_required_values(document, legacy, qde)
        self.assertEqual(content["value_losses"], [])
        self.assertEqual(content["unverified"], [])

    def test_short_names_are_not_flagged(self) -> None:
        document = _fake_document("d1", item_name="—")
        text = "010126/0001/1 шт 1"
        content = _check_required_values(document, text, text)
        self.assertEqual(content["value_losses"], [])
        self.assertEqual(content["unverified"], [])


class ClassifyRowTests(SimpleTestCase):
    def _classify(self, **overrides):
        kwargs = {
            "pages_match": True,
            "media_box_match": True,
            "item_loss_count": 0,
            "item_duplication_count": 0,
            "value_losses": [],
            "unverified": [],
            "totals_missing": False,
            "legacy_empty_pages": 0,
            "qde_empty_pages": 0,
            "identity_violation": "",
            "extraction_error": "",
        }
        kwargs.update(overrides)
        return _classify_row(**kwargs)

    def test_clean_row_is_match(self) -> None:
        reasons, verdict, primary = self._classify()
        self.assertEqual(reasons, [])
        self.assertEqual(verdict, "MATCH")
        self.assertEqual(primary, "")

    def test_page_difference_is_review_required(self) -> None:
        reasons, verdict, primary = self._classify(pages_match=False)
        self.assertEqual(reasons, ["PAGE_COUNT_DIFF"])
        self.assertEqual(verdict, "REVIEW_REQUIRED")
        self.assertEqual(primary, "PAGE_COUNT_DIFF")

    def test_media_box_only_is_mismatch(self) -> None:
        _reasons, verdict, primary = self._classify(media_box_match=False)
        self.assertEqual(verdict, "MISMATCH")
        self.assertEqual(primary, "MEDIA_BOX_DIFF")

    def test_content_loss_outranks_page_difference(self) -> None:
        reasons, verdict, primary = self._classify(
            pages_match=False,
            item_loss_count=1,
            value_losses=["item:Болт"],
        )
        self.assertEqual(verdict, "REVIEW_REQUIRED")
        self.assertEqual(primary, "TEXT_REQUIRED_MISSING")
        self.assertIn("PAGE_COUNT_DIFF", reasons)

    def test_identity_violation_is_primary(self) -> None:
        _, verdict, primary = self._classify(
            pages_match=False,
            identity_violation="template_version: expected='2.2.0' actual='2.1.0'; ",
        )
        self.assertEqual(verdict, "REVIEW_REQUIRED")
        self.assertEqual(primary, "IDENTITY_VIOLATION")

    def test_empty_page_reason(self) -> None:
        reasons, _, _ = self._classify(qde_empty_pages=1, legacy_empty_pages=0)
        self.assertIn("EMPTY_PAGE", reasons)

    def test_unverified_text_reason(self) -> None:
        reasons, _, primary = self._classify(unverified=["item:Шайба"])
        self.assertIn("TEXT_UNVERIFIED", reasons)
        self.assertEqual(primary, "TEXT_UNVERIFIED")


class RowSchemaTests(SimpleTestCase):
    def test_blank_row_has_canonical_schema(self) -> None:
        self.assertEqual(set(_blank_result("doc-1").keys()), set(RESULT_FIELDS))

    def test_failure_row_has_canonical_schema(self) -> None:
        row = Command()._failure_row("doc-1", "FETCH_FAILED", "boom", _expected_axes())
        self.assertEqual(set(row.keys()), set(RESULT_FIELDS))
        self.assertEqual(row["expected_template_version"], "2.2.0")


class SummaryTests(SimpleTestCase):
    def test_distributions_and_version_assertion(self) -> None:
        rows = [
            _blank_result(
                "d1",
                verdict="MATCH",
                pages_match=True,
                media_box_match=True,
                text_match=True,
                pages_delta=0,
                actual_template_version="2.2.0",
                total_shadow_duration_ms=10,
            ),
            _blank_result(
                "d2",
                verdict="REVIEW_REQUIRED",
                pages_match=False,
                media_box_match=True,
                text_match=False,
                pages_delta=1,
                review_reasons="PAGE_COUNT_DIFF|TEXT_REQUIRED_MISSING",
                review_primary_reason="TEXT_REQUIRED_MISSING",
                item_loss_count=1,
                actual_template_version="2.2.0",
                total_shadow_duration_ms=20,
            ),
            _blank_result(
                "d3",
                verdict="MISMATCH",
                pages_match=True,
                media_box_match=False,
                text_match=True,
                review_reasons="MEDIA_BOX_DIFF",
                review_primary_reason="MEDIA_BOX_DIFF",
                actual_template_version="2.1.0",
                total_shadow_duration_ms=30,
            ),
        ]
        summary = _build_summary(
            rows,
            corpus=_summary_corpus(),
            expected_axes=_expected_axes(),
            expect_template_version="2.2.0",
        )
        self.assertEqual(summary["match"], 1)
        self.assertEqual(summary["review_required"], 1)
        self.assertEqual(summary["mismatch"], 1)
        self.assertEqual(summary["pages_match_ratio"], "66.7%")
        self.assertIn("diagnostic only", summary["pages_match_note"])
        self.assertEqual(summary["review_reasons_distribution"]["PAGE_COUNT_DIFF"], 1)
        self.assertEqual(summary["review_reasons_distribution"]["MEDIA_BOX_DIFF"], 1)
        self.assertEqual(summary["review_primary_distribution"]["TEXT_REQUIRED_MISSING"], 1)
        self.assertEqual(summary["pages_delta_distribution"], {"0": 1, "1": 1})
        self.assertEqual(summary["item_loss_rows"], 1)
        self.assertEqual(summary["actual_template_version_counts"], {"2.2.0": 2, "2.1.0": 1})
        self.assertFalse(summary["assertion"]["all_observed_identities_expected"])
        self.assertEqual(summary["assertion"]["violations"], ["d3"])
        self.assertIn("latency_ms", summary)


class CorpusFetchTests(SimpleTestCase):
    def test_fetch_paginates_without_trailing_slash(self) -> None:
        client = MagicMock()
        client.get.side_effect = [
            {"items": [{"id": "a"}, {"id": "b"}], "total": 3},
            {"items": [{"id": "c"}], "total": 3},
        ]
        documents, total, pages = Command()._fetch_documents(client, "waybill", 2)

        self.assertEqual([d["id"] for d in documents], ["a", "b", "c"])
        self.assertEqual(total, 3)
        self.assertEqual(pages, 2)
        self.assertEqual(client.get.call_count, 2)
        first_call = client.get.call_args_list[0]
        self.assertEqual(first_call.args[0], "/documents")
        self.assertEqual(first_call.kwargs["params"]["document_type"], "waybill")
        self.assertEqual(first_call.kwargs["params"]["offset"], 0)
        self.assertEqual(client.get.call_args_list[1].kwargs["params"]["offset"], 2)

    def test_fetch_rejects_unexpected_response(self) -> None:
        client = MagicMock()
        client.get.return_value = None
        with self.assertRaises(CommandError):
            Command()._fetch_documents(client, "waybill", 10)


@override_settings(DOCUMENT_TEMPLATE_MAP=TEMPLATE_MAP_220)
class CommandGuardTests(SimpleTestCase):
    @patch(f"{COMMAND_MODULE}.Command._fetch_documents")
    @patch("apps.sync_client.client.SyncServerClient")
    def test_template_version_mismatch_aborts_before_fetch(self, mock_client, mock_fetch) -> None:
        with (
            override_settings(DOCUMENT_TEMPLATE_MAP={"waybill": ("warehouse-waybill-ru", "2.1.0")}),
            self.assertRaisesMessage(CommandError, "Template version assertion failed"),
        ):
            call_command("collect_phase6d_evidence", "--dry-run")
        mock_fetch.assert_not_called()

    @patch(f"{COMMAND_MODULE}.Command._fetch_documents")
    @patch("apps.sync_client.client.SyncServerClient")
    def test_small_corpus_guard_blocks_run(self, mock_client, mock_fetch) -> None:
        mock_fetch.return_value = ([{"id": "a"}, {"id": "b"}], 2, 1)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesMessage(CommandError, "Corpus too small"):
                call_command("collect_phase6d_evidence", "--output-dir", tmp)
            self.assertEqual(os.listdir(tmp), [])

    @patch(f"{COMMAND_MODULE}.Command._fetch_documents")
    @patch("apps.sync_client.client.SyncServerClient")
    def test_guard_refuses_to_overwrite_existing_evidence(self, mock_client, mock_fetch) -> None:
        mock_fetch.return_value = ([{"id": f"d{i}"} for i in range(MIN_SMALL_CORPUS_GUARD)], MIN_SMALL_CORPUS_GUARD, 1)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "phase6d-summary.json"), "w", encoding="utf-8") as handle:
                handle.write("{}")
            with self.assertRaisesMessage(CommandError, "Refusing to overwrite"):
                call_command("collect_phase6d_evidence", "--output-dir", tmp)

    @patch(f"{COMMAND_MODULE}.Command._fetch_documents")
    @patch("apps.sync_client.client.SyncServerClient")
    def test_dry_run_writes_nothing(self, mock_client, mock_fetch) -> None:
        mock_fetch.return_value = ([{"id": f"d{i}"} for i in range(MIN_SMALL_CORPUS_GUARD)], MIN_SMALL_CORPUS_GUARD, 1)
        with tempfile.TemporaryDirectory() as tmp:
            out = MagicMock()
            call_command("collect_phase6d_evidence", "--dry-run", "--output-dir", tmp, stdout=out)
            self.assertEqual(os.listdir(tmp), [])
            printed = "".join(call.args[0] for call in out.write.call_args_list)
            self.assertIn("DRY RUN", printed)
            self.assertIn("documents_to_process", printed)

    @patch(f"{COMMAND_MODULE}._git_info")
    @patch(f"{COMMAND_MODULE}._extract_pdf_text")
    @patch(f"{COMMAND_MODULE}.compare_pdf_structural")
    @patch(f"{COMMAND_MODULE}.render_shadow_pdf")
    @patch(f"{COMMAND_MODULE}.render_document_pdf")
    @patch(f"{COMMAND_MODULE}.DocumentsAPI")
    @patch(f"{COMMAND_MODULE}.Command._fetch_documents")
    @patch("apps.sync_client.client.SyncServerClient")
    def test_full_run_writes_uniform_evidence(
        self,
        mock_client,
        mock_fetch,
        mock_api_cls,
        mock_legacy_render,
        mock_shadow_render,
        mock_compare,
        mock_extract,
        mock_git,
    ) -> None:
        documents = [_fake_document("doc-1"), _fake_document("doc-2")]
        mock_fetch.return_value = ([{"id": "doc-1"}, {"id": "doc-2"}], 2, 1)
        mock_api_cls.return_value.get_document.side_effect = (
            lambda doc_id: next(doc for doc in documents if doc["id"] == doc_id)
        )

        artifact = SimpleNamespace(
            id=10,
            template_id="warehouse-waybill-ru",
            template_version="2.2.0",
            document_contract="warehouse.operation-document/v2",
            engine="qde",
            engine_version="1.0.0",
            backend="typst",
            backend_version="0.15.1",
        )
        mock_legacy_render.side_effect = lambda document: SimpleNamespace(
            pdf_bytes=b"%PDF-legacy-" + document["id"].encode(),
            artifact=SimpleNamespace(id=100),
            cache_hit=False,
        )
        mock_shadow_render.side_effect = lambda document: SimpleNamespace(
            pdf_bytes=b"%PDF-shadow-" + document["id"].encode(),
            artifact=artifact,
            cache_hit=False,
        )
        mock_compare.return_value = {
            "sha_match": False,
            "legacy_page_count": 1,
            "shadow_page_count": 1,
            "page_count_match": True,
            "legacy_media_box": [0.0, 0.0, 595.275591, 841.889764],
            "shadow_media_box": [0.0, 0.0, 595.2756, 841.8898],
            "media_box_match": True,
        }
        good_text = "010126/0001/1 Ложка чайная шт 1 Итого 1"

        def _extract(pdf_bytes: bytes):
            if pdf_bytes.startswith(b"%PDF-shadow-") and pdf_bytes.endswith(b"doc-2"):
                return good_text.replace("Ложка чайная", ""), 1, 0
            return good_text, 1, 0

        mock_extract.side_effect = _extract
        mock_git.return_value = {"git_sha": "deadbeef", "git_branch": "dev", "git_dirty": True}

        with tempfile.TemporaryDirectory() as tmp:
            call_command("collect_phase6d_evidence", "--output-dir", tmp, "--allow-small-corpus", stdout=MagicMock())

            with open(os.path.join(tmp, "phase6d-comparisons.json"), encoding="utf-8") as handle:
                rows = json.load(handle)
            with open(os.path.join(tmp, "phase6d-summary.json"), encoding="utf-8") as handle:
                summary = json.load(handle)
            with open(os.path.join(tmp, "phase6d-run-manifest.json"), encoding="utf-8") as handle:
                manifest = json.load(handle)
            with open(os.path.join(tmp, "phase6d-comparisons.csv"), encoding="utf-8") as handle:
                header = next(csv.reader(handle))

        self.assertEqual(len(rows), 2)
        self.assertTrue(all(set(row.keys()) == set(RESULT_FIELDS) for row in rows))
        self.assertTrue(all(row["actual_template_version"] == "2.2.0" for row in rows))
        self.assertEqual(summary["match"], 1)
        self.assertEqual(summary["review_required"], 1)
        self.assertEqual(summary["review_primary_distribution"], {"TEXT_REQUIRED_MISSING": 1})
        self.assertTrue(summary["assertion"]["all_observed_identities_expected"])
        self.assertEqual(manifest["expected_template_version"], "2.2.0")
        self.assertEqual(manifest["warehouse_web"]["git_sha"], "deadbeef")
        self.assertEqual(manifest["corpus"]["processed"], 2)
        self.assertEqual(header, list(RESULT_FIELDS))


class LoadDocumentIdsTests(SimpleTestCase):
    def _write(self, tmp: str, name: str, content: str) -> str:
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def test_json_array_and_line_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            json_path = self._write(tmp, "ids.json", '["a", "b ", " c "]')
            line_path = self._write(tmp, "ids.txt", "a\n\nb ,\nc\n")
            self.assertEqual(_load_document_ids(json_path), {"a", "b", "c"})
            self.assertEqual(_load_document_ids(line_path), {"a", "b", "c"})

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "ids.json", "[not-json")
            with self.assertRaisesMessage(CommandError, "Invalid JSON"):
                _load_document_ids(path)

    def test_missing_file_raises(self) -> None:
        with self.assertRaisesMessage(CommandError, "Cannot read"):
            _load_document_ids("/nonexistent/ids.txt")


@override_settings(DOCUMENT_TEMPLATE_MAP=TEMPLATE_MAP_220)
class DocumentIdsFilterTests(SimpleTestCase):
    @patch(f"{COMMAND_MODULE}.Command._fetch_documents")
    @patch("apps.sync_client.client.SyncServerClient")
    def test_document_ids_file_filters_corpus(self, mock_client, mock_fetch) -> None:
        mock_fetch.return_value = ([{"id": "a"}, {"id": "b"}, {"id": "c"}], 3, 1)
        with tempfile.TemporaryDirectory() as tmp:
            ids_path = os.path.join(tmp, "ids.txt")
            with open(ids_path, "w", encoding="utf-8") as handle:
                handle.write("c\na\n")
            out = MagicMock()
            call_command(
                "collect_phase6d_evidence",
                "--dry-run",
                "--output-dir", tmp,
                "--document-ids-file", ids_path,
                stdout=out,
            )
        printed = "".join(call.args[0] for call in out.write.call_args_list)
        self.assertIn("Corpus filter: 2/3", printed)
        self.assertIn("documents_to_process: 2", printed)

    @patch(f"{COMMAND_MODULE}.Command._fetch_documents")
    @patch("apps.sync_client.client.SyncServerClient")
    def test_unknown_document_id_aborts(self, mock_client, mock_fetch) -> None:
        mock_fetch.return_value = ([{"id": "a"}], 1, 1)
        with tempfile.TemporaryDirectory() as tmp:
            ids_path = os.path.join(tmp, "ids.txt")
            with open(ids_path, "w", encoding="utf-8") as handle:
                handle.write("a\nmissing-id\n")
            with self.assertRaisesMessage(CommandError, "not found in the fetched corpus"):
                call_command(
                    "collect_phase6d_evidence",
                    "--dry-run",
                    "--output-dir", tmp,
                    "--document-ids-file", ids_path,
                )
