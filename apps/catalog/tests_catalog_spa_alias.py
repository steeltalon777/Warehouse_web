from __future__ import annotations

import uuid
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.users.models import SyncUserBinding


def _ok(data):
    return SimpleNamespace(ok=True, data=data, form_error="")


class CatalogSpaAliasBaseTestCase(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._spa_dir = TemporaryDirectory()
        dist = Path(cls._spa_dir.name)
        (dist / "index.html").write_text(
            """<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\">
    <link rel=\"stylesheet\" href=\"styles.css\">
  </head>
  <body>
    <app-root></app-root>
    <script src=\"main.js\" type=\"module\"></script>
  </body>
</html>
""",
            encoding="utf-8",
        )
        cls._settings_override = override_settings(FRONTEND_BUILD_DIR=cls._spa_dir.name)
        cls._settings_override.enable()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._settings_override.disable()
        cls._spa_dir.cleanup()
        super().tearDownClass()

    def create_user(self, username: str, *, role: str = "observer", is_superuser: bool = False):
        user = get_user_model().objects.create_user(
            username=username,
            password="testpass123",
            is_active=True,
            is_superuser=is_superuser,
        )
        SyncUserBinding.objects.create(
            user=user,
            syncserver_user_id=uuid.uuid4(),
            sync_user_token=f"token-{username}",
            sync_role=role,
        )
        return user

    def force_login_with_role(self, user) -> None:
        self.client.force_login(user)
        session = self.client.session
        session["sync_role"] = getattr(user.sync_binding, "sync_role", "")
        session["sync_user_token"] = f"token-{user.username}"
        session["sync_user_id"] = str(uuid.uuid4())
        session["sync_is_root"] = user.is_superuser or session["sync_role"] == "root"
        session["sync_available_sites"] = []
        session["sync_default_site_id"] = ""
        session.save()

    def _browse_items(self) -> list[dict]:
        return [
            {
                "id": "10",
                "name": "Кабель",
                "sku": "SKU-10",
                "category_id": "1",
                "category_name": "Кабели",
                "unit_symbol": "шт",
                "hashtags": [],
                "is_active": True,
            }
        ]

    def _browse_service_mock(self) -> Mock:
        items = self._browse_items()
        return Mock(
            list_categories=Mock(return_value=_ok([{"id": "1", "name": "Кабели"}])),
            browse_all_items=Mock(return_value=_ok(items)),
            browse_items=Mock(
                return_value=_ok(
                    {
                        "items": items,
                        "page": 1,
                        "page_size": 20,
                        "total_count": len(items),
                    }
                )
            ),
        )

    def _manage_service_mock(self) -> Mock:
        return Mock(
            list_admin_categories=Mock(return_value=_ok([{"id": "1", "name": "Кабели"}])),
            browse_all_items=Mock(return_value=_ok(self._browse_items())),
        )

    def patch_ssr_services(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch(
                "apps.catalog.browse_views._build_catalog_service",
                return_value=self._browse_service_mock(),
            )
        )
        stack.enter_context(
            patch(
                "apps.catalog.views._build_catalog_service",
                return_value=self._manage_service_mock(),
            )
        )
        return stack


class CatalogSpaAliasAuthTests(CatalogSpaAliasBaseTestCase):
    def test_anonymous_catalog_and_nomenclature_redirect_to_login(self) -> None:
        for path in ("/catalog/", "/nomenclature/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])
                self.assertIn(f"next={path}", response["Location"])

    def test_authenticated_observer_can_open_catalog_paths(self) -> None:
        user = self.create_user("catalog_viewer", role="observer")
        self.force_login_with_role(user)

        with self.patch_ssr_services():
            for path in (
                "/catalog/",
                "/catalog/items/",
                "/catalog/categories/",
            ):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertNotIn("/login/", response.headers.get("Location", ""))

            response = self.client.get("/catalog/ssr/")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("/login/", response.headers.get("Location", ""))

    def test_authenticated_observer_nomenclature_redirects_to_catalog(self) -> None:
        user = self.create_user("catalog_observer", role="observer")
        self.force_login_with_role(user)

        response = self.client.get("/nomenclature/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/catalog/")

    def test_chief_can_open_nomenclature(self) -> None:
        user = self.create_user("chief_catalog_manager", role="chief_storekeeper")
        self.force_login_with_role(user)

        response = self.client.get("/nomenclature/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("/login/", response.headers.get("Location", ""))

    def test_root_can_open_nomenclature(self) -> None:
        user = self.create_user("root_catalog_manager", role="root", is_superuser=True)
        self.force_login_with_role(user)

        response = self.client.get("/nomenclature/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("/login/", response.headers.get("Location", ""))


class CatalogSpaAliasSidebarRenderingTests(CatalogSpaAliasBaseTestCase):
    def test_non_manager_sidebar_hides_manager_only_links(self) -> None:
        user = self.create_user("observer_sidebar", role="observer")
        self.force_login_with_role(user)

        response = self.client.get("/catalog/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a href="/catalog/" class="sidebar-link-active">Каталог</a>', html=True)
        self.assertContains(response, "SSR / Legacy fallback")
        self.assertContains(response, 'href="/catalog/ssr/"')
        self.assertNotContains(response, 'href="/nomenclature/"')
        self.assertNotContains(response, 'href="/nomenclature/ssr/tree/"')

    def test_manager_sidebar_shows_nomenclature_and_legacy_links(self) -> None:
        user = self.create_user("chief_sidebar", role="chief_storekeeper")
        self.force_login_with_role(user)

        response = self.client.get("/catalog/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/nomenclature/"')
        self.assertContains(response, 'href="/catalog/ssr/"')
        self.assertContains(response, 'href="/nomenclature/ssr/tree/"')
        self.assertContains(response, 'href="/nomenclature/ssr/items/"')
        self.assertContains(response, 'href="/nomenclature/ssr/categories/"')
        self.assertContains(response, 'href="/nomenclature/ssr/units/"')


class CatalogSpaAliasSidebarStateTests(CatalogSpaAliasBaseTestCase):
    def test_catalog_spa_route_marks_primary_catalog_active(self) -> None:
        user = self.create_user("observer_catalog_active", role="observer")
        self.force_login_with_role(user)

        response = self.client.get("/catalog/")
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a href="/catalog/" class="sidebar-link-active">Каталог</a>', html=True)
        self.assertNotContains(
            response,
            '<a href="/catalog/ssr/" class="sidebar-link-active">Каталог SSR legacy fallback</a>',
            html=True,
        )
        self.assertIn('<details class="sidebar-details">', html)

    def test_catalog_ssr_route_opens_legacy_section_and_shows_banner(self) -> None:
        user = self.create_user("observer_catalog_legacy", role="observer")
        self.force_login_with_role(user)

        with self.patch_ssr_services():
            response = self.client.get("/catalog/ssr/")

        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<a href="/catalog/" class="sidebar-link-active">Каталог</a>', html=True)
        self.assertContains(
            response,
            '<a href="/catalog/ssr/" class="sidebar-link-active">Каталог SSR legacy fallback</a>',
            html=True,
        )
        self.assertContains(
            response,
            '<summary class="sidebar-nested-title sidebar-link-active">SSR / Legacy fallback</summary>',
            html=True,
        )
        self.assertIn('<details class="sidebar-details" open>', html)
        self.assertContains(response, "Legacy SSR fallback: этот экран сохранён для совместимости")

    def test_nomenclature_spa_subroute_marks_nomenclature_active(self) -> None:
        user = self.create_user("chief_nomenclature_active", role="chief_storekeeper")
        self.force_login_with_role(user)

        response = self.client.get("/nomenclature/some/path")
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a href="/nomenclature/" class="sidebar-link-active">Номенклатура</a>', html=True)
        self.assertIn('<details class="sidebar-details">', html)

    def test_nomenclature_ssr_route_opens_legacy_section(self) -> None:
        user = self.create_user("chief_nomenclature_legacy", role="chief_storekeeper")
        self.force_login_with_role(user)

        with self.patch_ssr_services():
            response = self.client.get("/nomenclature/ssr/tree/")

        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<a href="/nomenclature/" class="sidebar-link-active">Номенклатура</a>', html=True)
        self.assertContains(response, '<a href="/nomenclature/ssr/tree/" class="sidebar-link-active">Дерево SSR</a>', html=True)
        self.assertContains(
            response,
            '<summary class="sidebar-nested-title sidebar-link-active">SSR / Legacy fallback</summary>',
            html=True,
        )
        self.assertIn('<details class="sidebar-details" open>', html)
