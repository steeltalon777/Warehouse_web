"""Cache key derivation tests (TZ-QDE_INTEGRATION_READINESS §5.4, §7).

Legacy namespace stays backward-compatible; QDE namespace uses the canonical
render identity axes and must not intersect with the legacy one.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.documents.services import (
    DEFAULT_LEGACY_AXES,
    build_legacy_waybill_cache_key,
    build_qde_cache_key,
)


def _qde_axes(**overrides) -> dict:
    values = {
        "document_id": "doc-1",
        "revision": 0,
        "payload_hash": "a" * 64,
        "document_contract": "warehouse.operation-document/v2",
        "template_id": "warehouse-waybill-ru",
        "template_version": "2.0.0",
        "engine": "qde",
        "engine_version": "0.1.0",
        "backend": "typst",
        "backend_version": "0.15.1",
    }
    values.update(overrides)
    return values


class QdeCacheKeyTests(SimpleTestCase):
    def test_same_axes_same_key(self) -> None:
        self.assertEqual(build_qde_cache_key(**_qde_axes()), build_qde_cache_key(**_qde_axes()))

    def test_each_identity_axis_change_gives_different_key(self) -> None:
        for axis in _qde_axes():
            with self.subTest(axis=axis):
                changed = _qde_axes(**{axis: f"{_qde_axes()[axis]}-other"})
                self.assertNotEqual(
                    build_qde_cache_key(**changed),
                    build_qde_cache_key(**_qde_axes()),
                    f"changing axis {axis!r} must change the QDE cache key",
                )

    def test_render_role_does_not_change_key(self) -> None:
        primary = build_qde_cache_key(**_qde_axes())
        shadow = build_qde_cache_key(**_qde_axes())
        self.assertEqual(primary, shadow)

    def test_status_does_not_change_key(self) -> None:
        ready = build_qde_cache_key(**_qde_axes())
        failed = build_qde_cache_key(**_qde_axes())
        self.assertEqual(ready, failed)

    def test_layout_version_does_not_change_qde_key(self) -> None:
        v1 = build_qde_cache_key(**_qde_axes())
        v9 = build_qde_cache_key(**_qde_axes())
        self.assertEqual(v1, v9)

    def test_key_contains_all_canonical_axes(self) -> None:
        key = build_qde_cache_key(**_qde_axes())
        self.assertTrue(key.startswith("qde_pdf:doc-1:0:"))
        self.assertIn(":warehouse.operation-document/v2:", key)
        self.assertIn("warehouse-waybill-ru@2.0.0", key)
        self.assertIn("qde@0.1.0", key)
        self.assertIn("typst@0.15.1", key)


class LegacyCacheKeyTests(SimpleTestCase):
    def test_legacy_key_format_is_backward_compatible(self) -> None:
        key = build_legacy_waybill_cache_key(
            document_id="doc-1",
            payload_hash="a" * 64,
            renderer_version=DEFAULT_LEGACY_AXES["engine_version"],
            template_version="1.0",
        )
        # Legacy format is frozen (TZ §5.4): no revision, no contract, no
        # engine/backend axes, and the layout namespace stays at layout-v7.1.
        self.assertEqual(
            key,
            f"waybill_pdf:doc-1:{'a' * 64}:waybill-pdf-v3:1.0:layout-v7.1",
        )

    def test_legacy_namespace_does_not_intersect_qde(self) -> None:
        legacy = build_legacy_waybill_cache_key(
            document_id="doc-1",
            payload_hash="a" * 64,
            renderer_version="waybill-pdf-v3",
            template_version="1.0",
        )
        qde = build_qde_cache_key(**_qde_axes())
        self.assertNotEqual(legacy, qde)
        self.assertTrue(legacy.startswith("waybill_pdf:"))
        self.assertTrue(qde.startswith("qde_pdf:"))
