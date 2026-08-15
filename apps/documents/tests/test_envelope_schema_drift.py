"""Schema-drift guard: bundled envelope schema must match the QDE canonical one.

Warehouse_web bundles a copy of the canonical QDE envelope schema at
``apps/documents/qde/envelope_v1.schema.json`` (used for jsonschema
validation in ``build_qde_envelope``, TZ §7.3). This test compares that
bundled copy against the authoritative source
``QuartermasterDocumentEngine/contracts/envelope/v1/envelope.schema.json``
(ADR-0032 D1) so a schema change in QDE fails CI instead of silently
drifting the BFF validation contract.

No third copy is introduced: the canonical file is read from the monorepo
checkout or from the installed QDE ``share/`` resources.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from django.test import SimpleTestCase

_BUNDLED_SCHEMA = Path(__file__).resolve().parents[1] / "qde" / "envelope_v1.schema.json"
# Monorepo layout: <workspace root>/QuartermasterDocumentEngine/contracts/...
_MONOREPO_CANONICAL = Path(__file__).resolve().parents[4] / "QuartermasterDocumentEngine" / "contracts" / "envelope" / "v1" / "envelope.schema.json"
# Installed QDE layout (pip install data-files, ADR-0032 D7): <sys.prefix>/share/...
_INSTALLED_CANONICAL = Path(sys.prefix) / "share" / "quartermaster_document_engine" / "contracts" / "envelope" / "v1" / "envelope.schema.json"


def _canonical_schema_path() -> Path:
    for candidate in (_MONOREPO_CANONICAL, _INSTALLED_CANONICAL):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Canonical QDE envelope schema not found; checked: "
        f"{_MONOREPO_CANONICAL}, {_INSTALLED_CANONICAL}"
    )


class EnvelopeSchemaDriftGuardTests(SimpleTestCase):
    def test_bundled_schema_matches_canonical(self) -> None:
        try:
            canonical_path = _canonical_schema_path()
        except FileNotFoundError as exc:
            self.fail(str(exc))

        with _BUNDLED_SCHEMA.open("r", encoding="utf-8") as bundled_file:
            bundled = json.load(bundled_file)
        with canonical_path.open("r", encoding="utf-8") as canonical_file:
            canonical = json.load(canonical_file)

        self.assertEqual(
            bundled,
            canonical,
            "Schema drift: Warehouse_web/apps/documents/qde/envelope_v1.schema.json "
            f"differs from canonical {canonical_path}. Update the bundled copy "
            "to match the QDE canonical envelope schema.",
        )
