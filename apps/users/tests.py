from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase
from django.urls import reverse


class LogoutViewTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="logout-user",
            password="test-pass-123",
        )

    def test_logout_allows_get_requests(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("users:logout"))

        self.assertRedirects(response, settings.LOGOUT_REDIRECT_URL)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_allows_post_requests(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(reverse("users:logout"))

        self.assertRedirects(response, settings.LOGOUT_REDIRECT_URL)
        self.assertNotIn("_auth_user_id", self.client.session)
