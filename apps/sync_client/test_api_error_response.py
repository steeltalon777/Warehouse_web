"""Tests for the structured proxy helper ``api_error_response``.

See TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS §8.5.
"""

from __future__ import annotations

import ast
import json
import pathlib

from django.test import SimpleTestCase

from apps.sync_client.api_error_response import (
    _FALLBACK_CODE,
    _FALLBACK_STATUS,
    _FALLBACK_TITLE,
    _FALLBACK_TYPE,
    api_error_response,
)
from apps.sync_client.exceptions import SyncConflictError, SyncServerAPIError


class ApiErrorResponseTests(SimpleTestCase):
    def test_dict_payload_passed_through(self) -> None:
        payload = {
            "type": "urn:warehouse:problem:operation-submit-rejected",
            "title": "Операция не проведена",
            "status": 409,
            "code": "insufficient_stock",
            "detail": "Недостаточно товара",
            "errors": [{"code": "insufficient_stock", "scope": "line_group"}],
        }
        exc = SyncConflictError("insufficient stock", status_code=409, payload=payload)

        response = api_error_response(exc)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.content), payload)

    def test_cancel_envelope_dict_detail_passed_through(self) -> None:
        # ADR-0027: cancel-flow envelope (dict detail with errors[]) must be
        # forwarded by api_error_response as-is, without ok/error wrapping.
        envelope = {
            "type": "urn:warehouse:problem:operation-cancel-rejected",
            "title": "Операция не может быть отменена",
            "status": 409,
            "code": "operation_cancel_rejected",
            "detail": "Недостаточно товара: Кабель ВВГ 3×2.5 — запрошено 2, на складе 0. Всего проблемных групп: 1.",
            "instance": "/api/v1/operations/op1/cancel",
            "errors": [
                {
                    "code": "insufficient_stock",
                    "scope": "line_group",
                    "operation_line_ids": [101],
                    "item": {"id": 17, "name": "Кабель ВВГ 3×2.5"},
                    "stock_site": {"id": 2, "name": "Склад Чита"},
                    "required_qty": "2.000",
                    "available_qty": "0.000",
                }
            ],
        }
        exc = SyncConflictError(
            "Недостаточно товара",
            status_code=409,
            payload=envelope,
        )

        response = api_error_response(exc)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.content), envelope)

    def test_http_status_preserved_and_none_falls_back(self) -> None:
        exc = SyncConflictError("conflict", status_code=409, payload={"detail": "conflict"})
        self.assertEqual(api_error_response(exc).status_code, 409)

        exc = SyncServerAPIError("missing status", status_code=None, payload={"detail": "x"})
        self.assertEqual(api_error_response(exc).status_code, 502)

    def test_invalid_status_falls_back_to_502(self) -> None:
        exc = SyncServerAPIError("bad status", status_code=200, payload={"detail": "x"})
        self.assertEqual(api_error_response(exc).status_code, 502)

    def test_none_payload_returns_fallback_envelope(self) -> None:
        exc = SyncServerAPIError("server hiccup", status_code=409, payload=None)

        response = api_error_response(exc)

        self.assertEqual(response.status_code, 502)
        body = json.loads(response.content)
        self.assertEqual(body["type"], _FALLBACK_TYPE)
        self.assertEqual(body["title"], _FALLBACK_TITLE)
        self.assertEqual(body["status"], _FALLBACK_STATUS)
        self.assertEqual(body["code"], _FALLBACK_CODE)
        self.assertEqual(body["detail"], "server hiccup")
        self.assertEqual(body["errors"], [])

    def test_string_payload_returns_fallback_envelope(self) -> None:
        exc = SyncServerAPIError("plain text error", status_code=409, payload="plain text")

        response = api_error_response(exc)

        self.assertEqual(response.status_code, 502)
        body = json.loads(response.content)
        self.assertEqual(body["type"], _FALLBACK_TYPE)
        self.assertEqual(body["code"], _FALLBACK_CODE)
        self.assertEqual(body["errors"], [])

    def test_list_payload_returns_fallback_envelope(self) -> None:
        exc = SyncServerAPIError("list payload", status_code=409, payload=[{"detail": "x"}])

        response = api_error_response(exc)

        self.assertEqual(response.status_code, 502)
        body = json.loads(response.content)
        self.assertEqual(body["type"], _FALLBACK_TYPE)
        self.assertEqual(body["code"], _FALLBACK_CODE)
        self.assertEqual(body["errors"], [])


class OtherSubmitEndpointsSnapshotTests(SimpleTestCase):
    """Snapshot: all operations BFF endpoints keep ``_handle_sync_error``
    except the submit endpoint, which now uses ``api_error_response``.
    """

    VIEWS_FILE = pathlib.Path(__file__).resolve().parents[1] / "bff_api" / "operations_views.py"

    EXPECTED_HELPERS = {
        "OperationsListView": "_handle_sync_error",
        "OperationDetailView": "_handle_sync_error",
        "OperationEffectiveAtView": "_handle_sync_error",
        "OperationSubmitView": "api_error_response",
        "OperationCancelView": "api_error_response",
        "OperationRestoreView": "_handle_sync_error",
        "OperationFromSourceDocumentView": "_handle_sync_error",
        "OperationAcceptLinesView": "_handle_sync_error",
    }

    @staticmethod
    def _extract_sync_error_helpers(source: str) -> dict[str, str]:
        tree = ast.parse(source)
        helpers: dict[str, str] = {}
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for try_node in ast.walk(item):
                    if not isinstance(try_node, ast.Try):
                        continue
                    for handler in try_node.handlers:
                        if not (
                            isinstance(handler.type, ast.Name)
                            and handler.type.id == "SyncServerAPIError"
                        ):
                            continue
                        helper = OtherSubmitEndpointsSnapshotTests._handler_helper(handler.body)
                        if helper is not None:
                            helpers[node.name] = helper
        return helpers

    @staticmethod
    def _handler_helper(body: list[ast.stmt]) -> str | None:
        for stmt in body:
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
                if isinstance(stmt.value.func, ast.Name):
                    return stmt.value.func.id
        return None

    def test_other_submit_endpoints_unchanged(self) -> None:
        source = self.VIEWS_FILE.read_text(encoding="utf-8")
        actual = self._extract_sync_error_helpers(source)
        self.assertEqual(actual, self.EXPECTED_HELPERS)
