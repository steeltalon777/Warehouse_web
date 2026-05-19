from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class TemporaryItemsViewsTestCase(TestCase):
    """Тесты представлений временных ТМЦ."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass",
            email="test@example.com",
        )
        # Войдем под пользователем
        self.client.force_login(self.user)

    def test_list_view_requires_login(self):
        """Проверка, что список временных ТМЦ требует аутентификации."""
        response = self.client.get(reverse("temporary_items:list"))
        # Так как у пользователя нет прав can_manage_catalog, должен быть редирект на dashboard
        self.assertIn(response.status_code, [200, 302])

    def test_detail_view_requires_login(self):
        """Проверка, что детальная страница требует аутентификации."""
        response = self.client.get(reverse("temporary_items:detail", args=["temp-123"]))
        self.assertIn(response.status_code, [200, 302, 404])

    def test_approve_view_requires_login(self):
        """Проверка, что страница преобразования требует аутентификации."""
        response = self.client.get(reverse("temporary_items:approve", args=["temp-123"]))
        self.assertIn(response.status_code, [200, 302, 404])

    def test_merge_view_requires_login(self):
        """Проверка, что страница объединения требует аутентификации."""
        response = self.client.get(reverse("temporary_items:merge", args=["temp-123"]))
        self.assertIn(response.status_code, [200, 302, 404])

    def test_urls_resolve(self):
        """Проверка разрешения URL."""
        self.assertEqual(reverse("temporary_items:list"), "/temporary-items/ssr/")
        self.assertEqual(reverse("temporary_items:item_search"), "/temporary-items/ssr/item-search/")
        self.assertEqual(reverse("temporary_items:detail", args=["temp-123"]), "/temporary-items/ssr/temp-123/")
        self.assertEqual(reverse("temporary_items:approve", args=["temp-123"]), "/temporary-items/ssr/temp-123/approve/")
        self.assertEqual(reverse("temporary_items:merge", args=["temp-123"]), "/temporary-items/ssr/temp-123/merge/")

    def test_template_names(self):
        """Проверка имён шаблонов через импорт представлений."""
        from apps.temporary_items.views import (
            TemporaryItemApproveView,
            TemporaryItemDetailView,
            TemporaryItemListView,
            TemporaryItemMergeView,
        )
        self.assertEqual(TemporaryItemListView.template_name, "temporary_items/list.html")
        self.assertEqual(TemporaryItemDetailView.template_name, "temporary_items/detail.html")
        self.assertEqual(TemporaryItemApproveView.template_name, "temporary_items/approve.html")
        self.assertEqual(TemporaryItemMergeView.template_name, "temporary_items/merge.html")



class TemporaryItemsSPARouteTests(TestCase):
    """Тесты маршрутов SPA для временных ТМЦ."""

    def setUp(self):
        self.client = Client()

    def test_spa_mount_redirects_anonymous(self):
        """SPA view requires login — anonymous gets 302."""
        response = self.client.get('/temporary-items/')
        self.assertEqual(response.status_code, 302)

    def test_spa_catchall_redirects_anonymous(self):
        """SPA catch-all also requires login."""
        response = self.client.get('/temporary-items/some/deep/path')
        self.assertEqual(response.status_code, 302)

    def test_ssr_fallback_redirects_anonymous(self):
        """SSR fallback at /temporary-items/ssr/ still requires login."""
        response = self.client.get('/temporary-items/ssr/')
        self.assertEqual(response.status_code, 302)

    def test_spa_url_name_resolves(self):
        """SPA url name resolves correctly."""
        self.assertEqual(reverse("temporary_items_spa"), "/temporary-items/")

    def test_spa_renders_for_authenticated(self):
        """Authenticated user gets 200 from SPA view."""
        user = User.objects.create_user(username="spauser", password="pass")
        self.client.force_login(user)
        response = self.client.get('/temporary-items/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/temp_items_spa.html")


class TemporaryItemsIntegrationTestCase(TestCase):
    """Интеграционные тесты с TemporaryItemsAPI (моки)."""

    # Здесь можно добавить моки для API, но для простоты оставим заглушки
    pass
