from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.users.models import SyncDeviceBinding


class DeviceAdminPanelRedirectTests(TestCase):
    def setUp(self) -> None:
        self.admin_user = get_user_model().objects.create_superuser(
            username="panel-admin",
            email="panel-admin@example.com",
            password="test-pass-123",
        )
        self.client.force_login(self.admin_user)

    def test_devices_page_redirects_to_django_admin(self) -> None:
        response = self.client.get(reverse("admin_panel:devices"))

        self.assertRedirects(response, reverse("admin:users_syncdevicebinding_changelist"))

    def test_device_create_redirects_to_django_admin_add(self) -> None:
        response = self.client.get(reverse("admin_panel:device_create"))

        self.assertRedirects(response, reverse("admin:users_syncdevicebinding_add"))

    def test_device_edit_redirects_to_local_admin_change(self) -> None:
        binding = SyncDeviceBinding.objects.create(
            device_code="DJANGO_WEB",
            device_name="Django Web Client",
            syncserver_device_id=17,
            is_active=True,
        )

        response = self.client.get(reverse("admin_panel:device_edit", args=[17]))

        self.assertRedirects(response, reverse("admin:users_syncdevicebinding_change", args=[binding.pk]))

    def test_device_edit_without_local_binding_redirects_to_admin_list(self) -> None:
        response = self.client.get(reverse("admin_panel:device_edit", args=[999]))

        self.assertRedirects(response, reverse("admin:users_syncdevicebinding_changelist"))
