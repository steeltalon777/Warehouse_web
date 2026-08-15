"""Unit tests for build_qde_envelope (TZ §10.1 Phase 6A, ADR-0032 D1/D2/D5)."""

from __future__ import annotations

import jsonschema
from django.test import SimpleTestCase, override_settings

from apps.documents.services import (
    ENVELOPE_SCHEMA,
    QdeValidationError,
    build_qde_envelope,
)

DEFAULT_DOCUMENT_TYPE = "waybill"
MAPPED_TEMPLATE_ID = "warehouse-waybill-ru"
MAPPED_TEMPLATE_VERSION = "2.0.0"


_MISSING = object()


def _document(payload: object = _MISSING, **overrides: object) -> dict:
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
            "lines": [
                {
                    "line_number": 1,
                    "item_name": "Дрель ударная",
                    "unit_symbol": "шт",
                    "quantity": 3.0,
                }
            ],
        },
    }
    if payload is not _MISSING:
        document["payload"] = payload
    document.update(overrides)
    return document


class BuildQdeEnvelopeTests(SimpleTestCase):
    def test_valid_envelope_from_well_formed_document(self) -> None:
        envelope = build_qde_envelope(_document())

        self.assertEqual(envelope["engine_contract_version"], "1.0.0")
        self.assertEqual(envelope["document_contract"], "warehouse.operation-document/v2")
        self.assertEqual(envelope["document_type"], "waybill")
        self.assertEqual(envelope["template_id"], MAPPED_TEMPLATE_ID)
        self.assertEqual(envelope["template_version"], MAPPED_TEMPLATE_VERSION)
        self.assertEqual(envelope["locale"], "ru-RU")
        self.assertEqual(envelope["render_profile"], "print")
        self.assertEqual(envelope["document_id"], "doc-1")
        self.assertEqual(envelope["document_number"], "WB-1")
        self.assertEqual(envelope["document"]["operation_display_number"], "060326/0121/1")
        # Envelope must satisfy the bundled QDE schema (TZ §7.3).
        jsonschema.validate(envelope, ENVELOPE_SCHEMA)

    def test_document_type_defaults_to_waybill(self) -> None:
        document = _document()
        del document["document_type"]
        envelope = build_qde_envelope(document)
        self.assertEqual(envelope["document_type"], "waybill")

    def test_missing_payload_raises_validation_error(self) -> None:
        document = _document(payload=None)
        with self.assertRaises(QdeValidationError):
            build_qde_envelope(document)

    def test_malformed_payload_raises_validation_error(self) -> None:
        document = _document(payload="not-a-dict")
        with self.assertRaises(QdeValidationError):
            build_qde_envelope(document)

    def test_unsupported_document_type_raises_validation_error(self) -> None:
        document = _document(document_type="fuel_report")
        with self.assertRaises(QdeValidationError):
            build_qde_envelope(document)

    def test_arbitrary_template_id_in_document_is_ignored(self) -> None:
        """SEC-10: client-supplied template_id must never influence the envelope."""
        document = _document(template_id="../../../etc/passwd")
        envelope = build_qde_envelope(document)
        self.assertEqual(envelope["template_id"], MAPPED_TEMPLATE_ID)
        self.assertNotIn("..", envelope["template_id"])

    def test_path_traversal_template_id_in_map_is_rejected(self) -> None:
        malicious_map = {"waybill": ("../../../etc/passwd", "2.0.0")}
        with self.assertRaises(QdeValidationError):
            build_qde_envelope(_document(), template_map=malicious_map)

    def test_template_id_with_path_separator_is_rejected(self) -> None:
        malicious_map = {"waybill": ("warehouse/waybill-ru", "2.0.0")}
        with self.assertRaises(QdeValidationError):
            build_qde_envelope(_document(), template_map=malicious_map)

    def test_template_id_with_double_dot_substring_is_rejected(self) -> None:
        malicious_map = {"waybill": ("warehouse..waybill", "2.0.0")}
        with self.assertRaises(QdeValidationError):
            build_qde_envelope(_document(), template_map=malicious_map)

    def test_unsafe_template_version_in_map_is_rejected(self) -> None:
        malicious_map = {"waybill": (MAPPED_TEMPLATE_ID, "../../2.0.0")}
        with self.assertRaises(QdeValidationError):
            build_qde_envelope(_document(), template_map=malicious_map)

    def test_template_map_override_wins_over_settings(self) -> None:
        custom_map = {"waybill": ("custom-waybill-ru", "1.0.0")}
        envelope = build_qde_envelope(_document(), template_map=custom_map)
        self.assertEqual(envelope["template_id"], "custom-waybill-ru")
        self.assertEqual(envelope["template_version"], "1.0.0")

    def test_empty_lines_payload_builds_and_validates(self) -> None:
        envelope = build_qde_envelope(_document(payload={"operation_type": "MOVE", "lines": []}))
        jsonschema.validate(envelope, ENVELOPE_SCHEMA)
        self.assertEqual(envelope["document"]["lines"], [])

    def test_long_and_empty_string_edge_cases_build_and_validate(self) -> None:
        payload = {
            "operation_display_number": "010101/0101/1",
            "operation_type": "MOVE",
            "lines": [
                {
                    "line_number": 1,
                    "item_name": "Наименование ТМЦ " * 100,
                    "unit_symbol": "",
                    "quantity": "0.00",
                },
                {"line_number": 2, "item_name": "", "unit_symbol": "шт", "quantity": 0},
            ],
            "sender": {"site_name": ""},
            "receiver": {"site_name": "База " * 500},
        }
        envelope = build_qde_envelope(_document(payload=payload))
        jsonschema.validate(envelope, ENVELOPE_SCHEMA)
        self.assertEqual(len(envelope["document"]["lines"]), 2)

    def test_document_id_and_number_omitted_when_missing(self) -> None:
        document = _document()
        del document["id"]
        del document["document_number"]
        envelope = build_qde_envelope(document)
        self.assertNotIn("document_id", envelope)
        self.assertNotIn("document_number", envelope)

    def test_settings_document_contract_is_used(self) -> None:
        with override_settings(QDE_DOCUMENT_CONTRACT="warehouse.operation-document/v3"):
            envelope = build_qde_envelope(_document())
        self.assertEqual(envelope["document_contract"], "warehouse.operation-document/v3")

    def test_default_map_contains_only_waybill_in_phase_6a(self) -> None:
        from django.conf import settings as django_settings

        self.assertEqual(set(django_settings.DOCUMENT_TEMPLATE_MAP), {"waybill"})
        self.assertEqual(django_settings.DOCUMENT_TEMPLATE_MAP["waybill"], (MAPPED_TEMPLATE_ID, MAPPED_TEMPLATE_VERSION))
        with self.assertRaises(QdeValidationError):
            build_qde_envelope(_document(document_type="acceptance_certificate"))
