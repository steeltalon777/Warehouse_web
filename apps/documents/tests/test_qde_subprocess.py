"""Unit tests for render_via_qde subprocess client (TZ §10.1 Phase 6A, ADR-0032 D3/D8)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.documents.services import (
    QDE_STDERR_CODE_TO_EXCEPTION,
    QdeAssetError,
    QdeBackendUnavailableError,
    QdeFontError,
    QdeRenderError,
    QdeRenderFailedError,
    QdeTemplateContractMismatchError,
    QdeTemplateError,
    QdeTimeoutError,
    QdeUnsupportedContractError,
    QdeValidationError,
    build_qde_envelope,
    build_qde_subprocess_env,
    render_via_qde,
)

PDF_BYTES = b"%PDF-1.4\n% qde test pdf\n"


def _document(**overrides: object) -> dict:
    document: dict = {
        "id": "doc-1",
        "document_type": "waybill",
        "document_number": "WB-1",
        "revision": 0,
        "site_id": 1,
        "template_name": "waybill_v1",
        "template_version": "1.0",
        "payload_hash": "a" * 64,
        "payload": {
            "operation_display_number": "060326/0121/1",
            "operation_type": "MOVE",
            "lines": [{"line_number": 1, "item_name": "Дрель ударная", "unit_symbol": "шт", "quantity": 3}],
        },
    }
    document.update(overrides)
    return document


def _completed(returncode: int, stderr: bytes = b"") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=b"", stderr=stderr)


def _stderr_for_code(code: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": f"boom {code}", "details": {"axis": "test"}}}).encode("utf-8")


def _fake_run_writing_output() -> SimpleNamespace:
    """Return a subprocess.run fake that writes a PDF at argv's --output path."""

    def fake_run(args, **kwargs):
        output_path = args[7]
        with open(output_path, "wb") as pdf_file:
            pdf_file.write(PDF_BYTES)
        return _completed(0)

    return fake_run


def _mkdtemp_fixed(path: str):
    def _mkdtemp(*args, **kwargs):
        os.makedirs(path, exist_ok=True)
        return path

    return _mkdtemp


def _fake_run_for_stderr_code(code: str):
    """Build a subprocess.run fake that exits non-zero with the given QDE stderr code."""

    def fake_run(args, **kwargs):
        return _completed(
            2 if code in ("INVALID_PAYLOAD", "UNSUPPORTED_ENGINE_CONTRACT", "UNSUPPORTED_DOCUMENT_CONTRACT", "UNSUPPORTED_OUTPUT_FORMAT") else 5,
            _stderr_for_code(code),
        )

    return fake_run


class RenderViaQdeTests(SimpleTestCase):
    def test_success_returns_pdf_bytes_with_canonical_argv(self) -> None:
        captured: dict = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            with open(args[5], "r", encoding="utf-8") as envelope_file:
                captured["envelope"] = json.load(envelope_file)
            output_path = args[7]
            with open(output_path, "wb") as pdf_file:
                pdf_file.write(PDF_BYTES)
            return _completed(0)

        with patch("apps.documents.services.subprocess.run", side_effect=fake_run):
            result = render_via_qde(_document())

        self.assertEqual(result.pdf_bytes, PDF_BYTES)
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.page_count)
        self.assertGreaterEqual(result.elapsed_seconds, 0.0)

        argv = captured["args"]
        self.assertEqual(argv[:5], ["python", "-m", "qm_cli.main", "render", "--input"])
        self.assertTrue(argv[5].startswith(tempfile.gettempdir()))
        self.assertIn("qde-", os.path.dirname(argv[5]))
        self.assertEqual(argv[6:8], ["--output", os.path.join(os.path.dirname(argv[5]), "output.pdf")])
        self.assertEqual(argv[8:], ["--format", "pdf"])
        self.assertEqual(captured["envelope"]["template_id"], "warehouse-waybill-ru")

    def test_no_shell_and_safe_whitelist_env(self) -> None:
        captured: dict = {}
        secret_key_env = "env-SECRET-KEY-UNIQUE"
        database_url_env = "postgres://user:env-secret@db/warehouse"

        def fake_run(args, **kwargs):
            captured["kwargs"] = kwargs
            with open(args[7], "wb") as pdf_file:
                pdf_file.write(PDF_BYTES)
            return _completed(0, b"")

        with patch.dict(os.environ, {"SECRET_KEY": secret_key_env, "DATABASE_URL": database_url_env}, clear=False), \
             override_settings(
                 QM_TEMPLATES_DIR="/opt/qde/templates",
                 QM_TYPST_BINARY="/usr/local/bin/typst",
                 QM_FONTS_DIR="/opt/qde/fonts",
                 TYPST_TIMESTAMP="1700000000",
             ), \
             patch("apps.documents.services.subprocess.run", side_effect=fake_run):
            render_via_qde(_document())

        run_env = captured["kwargs"]["env"]
        self.assertEqual(set(run_env.keys()), set(build_qde_subprocess_env().keys()))
        self.assertEqual(
            set(run_env.keys()),
            {"PATH", "LANG", "LC_ALL", "QM_TEMPLATES_DIR", "QM_TYPST_BINARY", "QM_FONTS_DIR", "TYPST_TIMESTAMP"},
        )
        # Values come from settings, not os.environ passthrough.
        self.assertEqual(run_env["QM_TEMPLATES_DIR"], "/opt/qde/templates")
        self.assertEqual(run_env["QM_TYPST_BINARY"], "/usr/local/bin/typst")
        self.assertEqual(run_env["QM_FONTS_DIR"], "/opt/qde/fonts")
        self.assertEqual(run_env["TYPST_TIMESTAMP"], "1700000000")
        # Secrets present in os.environ must NOT leak into the subprocess env.
        self.assertNotIn(secret_key_env, run_env.values())
        self.assertNotIn(database_url_env, run_env.values())
        # No shell=True anywhere (shell is explicitly False).
        self.assertIs(captured["kwargs"].get("shell"), False)

    def test_qde_error_codes_map_to_expected_exceptions(self) -> None:
        expected_status = {
            "INVALID_PAYLOAD": (QdeValidationError, 400),
            "UNSUPPORTED_ENGINE_CONTRACT": (QdeUnsupportedContractError, 400),
            "UNSUPPORTED_DOCUMENT_CONTRACT": (QdeUnsupportedContractError, 400),
            "UNSUPPORTED_OUTPUT_FORMAT": (QdeUnsupportedContractError, 400),
            "TEMPLATE_NOT_INSTALLED": (QdeTemplateError, 503),
            "TEMPLATE_VERSION_NOT_INSTALLED": (QdeTemplateError, 503),
            "TEMPLATE_CONTRACT_MISMATCH": (QdeTemplateContractMismatchError, 422),
            "BACKEND_NOT_AVAILABLE": (QdeBackendUnavailableError, 503),
            "FONT_NOT_AVAILABLE": (QdeFontError, 503),
            "ASSET_NOT_AVAILABLE": (QdeAssetError, 422),
            "RENDER_FAILED": (QdeRenderFailedError, 500),
        }

        for code, (exc_class, http_status) in expected_status.items():
            with self.subTest(code=code), patch(
                "apps.documents.services.subprocess.run", side_effect=_fake_run_for_stderr_code(code)
            ), self.assertRaises(exc_class) as ctx:
                render_via_qde(_document())
            self.assertEqual(ctx.exception.code, code)
            self.assertEqual(ctx.exception.http_status, http_status)
            self.assertIn(f"boom {code}", ctx.exception.message)

    def test_mapping_table_covers_all_eleven_codes(self) -> None:
        self.assertEqual(
            set(QDE_STDERR_CODE_TO_EXCEPTION),
            {
                "INVALID_PAYLOAD",
                "UNSUPPORTED_ENGINE_CONTRACT",
                "UNSUPPORTED_DOCUMENT_CONTRACT",
                "UNSUPPORTED_OUTPUT_FORMAT",
                "TEMPLATE_NOT_INSTALLED",
                "TEMPLATE_VERSION_NOT_INSTALLED",
                "TEMPLATE_CONTRACT_MISMATCH",
                "BACKEND_NOT_AVAILABLE",
                "FONT_NOT_AVAILABLE",
                "ASSET_NOT_AVAILABLE",
                "RENDER_FAILED",
            },
        )

    def test_exception_classes_carry_tz_http_mapping(self) -> None:
        self.assertEqual(QdeValidationError(code="INVALID_PAYLOAD", message="x").http_status, 400)
        self.assertEqual(QdeUnsupportedContractError(code="UNSUPPORTED_DOCUMENT_CONTRACT", message="x").http_status, 400)
        self.assertEqual(QdeTemplateError(code="TEMPLATE_NOT_INSTALLED", message="x").http_status, 503)
        self.assertEqual(QdeTemplateError(code="TEMPLATE_VERSION_NOT_INSTALLED", message="x").http_status, 503)
        self.assertEqual(QdeTemplateContractMismatchError(code="TEMPLATE_CONTRACT_MISMATCH", message="x").http_status, 422)
        self.assertEqual(QdeBackendUnavailableError(code="BACKEND_NOT_AVAILABLE", message="x").http_status, 503)
        self.assertEqual(QdeFontError(code="FONT_NOT_AVAILABLE", message="x").http_status, 503)
        self.assertEqual(QdeAssetError(code="ASSET_NOT_AVAILABLE", message="x").http_status, 422)
        self.assertEqual(QdeRenderFailedError(code="RENDER_FAILED", message="x").http_status, 500)
        self.assertEqual(QdeRenderFailedError(code="UNKNOWN_CODE", message="x").http_status, 500)

    def test_timeout_raises_qde_timeout_error(self) -> None:
        def fake_run(args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args, timeout=15)

        with patch("apps.documents.services.subprocess.run", side_effect=fake_run), self.assertRaises(QdeTimeoutError) as ctx:
            render_via_qde(_document())
        self.assertEqual(ctx.exception.http_status, 503)
        self.assertEqual(ctx.exception.retry_after, 5)
        self.assertIsInstance(ctx.exception, QdeRenderError)

    def test_missing_binary_raises_backend_unavailable(self) -> None:
        def fake_run(args, **kwargs):
            raise FileNotFoundError(2, "No such file or directory", "python")

        with patch("apps.documents.services.subprocess.run", side_effect=fake_run), self.assertRaises(QdeBackendUnavailableError) as ctx:
            render_via_qde(_document())
        self.assertEqual(ctx.exception.http_status, 503)
        self.assertEqual(ctx.exception.code, "BACKEND_NOT_AVAILABLE")

    def test_unparseable_stderr_raises_render_failed(self) -> None:
        def fake_run(args, **kwargs):
            return _completed(5, b"Traceback ... something broke, not json")

        with patch("apps.documents.services.subprocess.run", side_effect=fake_run), self.assertRaises(QdeRenderFailedError) as ctx:
            render_via_qde(_document())
        self.assertEqual(ctx.exception.http_status, 500)
        self.assertIn("not json", ctx.exception.message)

    def test_stderr_with_log_prefix_still_maps_error(self) -> None:
        def fake_run(args, **kwargs):
            stderr = b"2026-08-15 12:00:00 INFO render started\n" + _stderr_for_code("FONT_NOT_AVAILABLE")
            return _completed(4, stderr)

        with patch("apps.documents.services.subprocess.run", side_effect=fake_run), self.assertRaises(QdeFontError) as ctx:
            render_via_qde(_document())
        self.assertEqual(ctx.exception.code, "FONT_NOT_AVAILABLE")
        self.assertEqual(ctx.exception.http_status, 503)

    def test_exit_zero_without_pdf_raises_render_failed(self) -> None:
        def fake_run(args, **kwargs):
            return _completed(0, b"")

        with patch("apps.documents.services.subprocess.run", side_effect=fake_run), self.assertRaises(QdeRenderFailedError):
            render_via_qde(_document())

    def test_prebuilt_envelope_is_used(self) -> None:
        envelope = build_qde_envelope(_document())
        envelope["document"]["operation_type"] = "ISSUE"

        captured: dict = {}

        def fake_run(args, **kwargs):
            with open(args[5], "r", encoding="utf-8") as envelope_file:
                captured["envelope"] = json.load(envelope_file)
            with open(args[7], "wb") as pdf_file:
                pdf_file.write(PDF_BYTES)
            return _completed(0, b"")

        with patch("apps.documents.services.subprocess.run", side_effect=fake_run):
            render_via_qde(envelope=envelope)

        self.assertEqual(captured["envelope"]["document"]["operation_type"], "ISSUE")

    def test_requires_document_or_envelope(self) -> None:
        with self.assertRaises(QdeValidationError):
            render_via_qde()

    def test_temp_dir_removed_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = os.path.join(tmp, "qde-work")
            with patch("apps.documents.services.tempfile.mkdtemp", side_effect=_mkdtemp_fixed(workdir)), \
                 patch("apps.documents.services.subprocess.run", side_effect=_fake_run_writing_output()):
                result = render_via_qde(_document())
            self.assertEqual(result.pdf_bytes, PDF_BYTES)
            self.assertFalse(os.path.exists(workdir))

    def test_temp_dir_removed_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = os.path.join(tmp, "qde-work")
            with patch(
                "apps.documents.services.tempfile.mkdtemp", side_effect=_mkdtemp_fixed(workdir)
            ), patch(
                "apps.documents.services.subprocess.run",
                side_effect=lambda args, **kwargs: _completed(5, _stderr_for_code("RENDER_FAILED")),
            ), self.assertRaises(QdeRenderFailedError):
                render_via_qde(_document())
            self.assertFalse(os.path.exists(workdir))
