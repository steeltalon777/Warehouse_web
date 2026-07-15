from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.users.models import Site
from apps.users.services import SiteSyncService

User = get_user_model()


class SiteSyncServiceTests(TestCase):
    """SiteSyncService must not destroy local cache on partial/empty response."""

    def setUp(self):
        Site.objects.create(
            syncserver_site_id="100",
            code="WH-001", name="Warehouse 1",
        )
        Site.objects.create(
            syncserver_site_id="200",
            code="WH-002", name="Warehouse 2",
        )

    def test_initial_sites_preserved_on_empty_remote(self):
        """Empty remote snapshot does NOT delete existing local sites."""
        service = SiteSyncService()
        service.client = MagicMock()
        service.client.get.return_value = {"sites": [], "total_count": 0}

        count = service.refresh_local_cache()

        self.assertEqual(count, 0)
        self.assertEqual(Site.objects.count(), 2)

    def test_paginated_fetch_returns_all_pages(self):
        """Full pagination snapshot returns all sites."""
        service = SiteSyncService()
        service.client = MagicMock()
        service.client.get.return_value = {
            "sites": [{"site_id": 100, "code": "WH-001", "name": "WH1", "is_active": True}],
            "total_count": 1,
        }

        result = service.list_sites()
        self.assertEqual(len(result), 1)

    def test_no_delete_by_name(self):
        """Upsert does NOT delete sites by matching name."""
        Site.objects.create(
            syncserver_site_id="300",
            code="WH-003", name="Warehouse 3",
        )

        service = SiteSyncService()

        site = service._upsert_local_mirror({"site_id": 100, "code": "WH-001", "name": "Warehouse 1", "is_active": True})

        self.assertIsNotNone(site)
        self.assertTrue(Site.objects.filter(syncserver_site_id="300").exists())

    def test_duplicate_snapshot_rejected(self):
        """Malformed snapshot (missing site_id) raises error."""
        service = SiteSyncService()
        with self.assertRaises(ValueError):
            service._upsert_local_mirror({"code": "NO-ID", "name": "No ID Site"})


class SiteAdminTests(TestCase):
    """SiteAdmin must not call SyncServer on GET changelist."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="site-admin", password="Admin123",
        )
        Site.objects.create(code="EXISTING", name="Existing Site", syncserver_site_id="999")

    def test_changelist_get_does_not_sync(self):
        """GET changelist returns sites without calling SyncServer."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:users_site_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Existing Site")
