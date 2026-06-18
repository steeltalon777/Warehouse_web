"""
Playwright smoke tests for the Nomenclature SPA.

These tests verify that:
1. Authenticated users can access the nomenclature SPA.
2. The bootstrap API loads successfully.
3. No direct SyncServer calls are made from the browser (all traffic goes through Django BFF).

Run with: pytest tests_e2e/ --headed  (or use pytest-playwright plugin)
"""

import re
import os

import pytest

# ---------------------------------------------------------------------------
# Configuration — read from environment so secrets are never hard-coded.
# ---------------------------------------------------------------------------
DJANGO_BASE_URL = os.environ.get("DJANGO_BASE_URL", "http://localhost:8000")
SYNC_SERVER_BASE_URL = os.environ.get("SYNC_SERVER_BASE_URL", "http://localhost:9000")
TEST_USERNAME = os.environ.get("TEST_USERNAME", "test_spa_user")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "test_spa_password")


@pytest.fixture(scope="session")
def django_base_url() -> str:
    return DJANGO_BASE_URL


@pytest.fixture(scope="session")
def sync_server_url() -> str:
    return SYNC_SERVER_BASE_URL


# ---------------------------------------------------------------------------
# Helper: log in via the Django login page.
# ---------------------------------------------------------------------------
def login(page, username: str, password: str, login_url: str = "/users/login/") -> None:
    """Navigate to the Django login page and authenticate."""
    page.goto(login_url, wait_until="networkidle")
    # Common Django login form field names — adjust if your template differs.
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"], input[type="submit"]')
    page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestNomenclatureSPAAccess:
    """Verify that the nomenclature SPA requires authentication."""

    def test_anonymous_redirected_to_login(self, page, django_base_url: str) -> None:
        """Anonymous access to /nomenclature/ should redirect to login."""
        response = page.goto(f"{django_base_url}/nomenclature/", wait_until="networkidle")
        # Django redirects anonymous users; the final URL should contain "login"
        assert "login" in page.url.lower(), (
            f"Expected redirect to login page, but landed on {page.url}"
        )

    def test_authenticated_user_can_access_spa(
        self, page, django_base_url: str
    ) -> None:
        """Authenticated user should get the SPA shell at /nomenclature/."""
        login(page, TEST_USERNAME, TEST_PASSWORD)
        response = page.goto(f"{django_base_url}/nomenclature/", wait_until="networkidle")
        assert response is not None
        assert response.status == 200, (
            f"Expected 200 for authenticated SPA access, got {response.status}"
        )


class TestBootstrapAPI:
    """Verify that the bootstrap API endpoint works correctly."""

    def test_bootstrap_returns_json_with_expected_keys(
        self, page, django_base_url: str
    ) -> None:
        """The bootstrap API should return JSON with categories_tree, items, units, user, permissions."""
        login(page, TEST_USERNAME, TEST_PASSWORD)

        # Listen for the bootstrap API response
        bootstrap_response = None

        def on_response(resp):
            nonlocal bootstrap_response
            if "/nomenclature/api/bootstrap/" in resp.url:
                bootstrap_response = resp

        page.on("response", on_response)

        page.goto(f"{django_base_url}/nomenclature/", wait_until="networkidle")

        assert bootstrap_response is not None, (
            "Bootstrap API request was not detected. "
            "Ensure the SPA calls /nomenclature/api/bootstrap/ on load."
        )
        assert bootstrap_response.status == 200, (
            f"Bootstrap API returned {bootstrap_response.status}"
        )

        content_type = bootstrap_response.header_value("content-type") or ""
        assert "json" in content_type, (
            f"Expected JSON content type, got: {content_type}"
        )

        body = bootstrap_response.json()
        assert body.get("ok") is True, f"Bootstrap response not ok: {body}"

        data = body.get("data", {})
        required_keys = {"categories_tree", "items", "units", "user", "permissions"}
        missing = required_keys - set(data.keys())
        assert not missing, f"Bootstrap JSON missing keys: {missing}"

    def test_bootstrap_anonymous_redirected(
        self, page, django_base_url: str
    ) -> None:
        """Anonymous bootstrap request should redirect to login."""
        response = page.goto(
            f"{django_base_url}/nomenclature/api/bootstrap/",
            wait_until="networkidle",
        )
        assert response is not None
        assert response.status in (301, 302), (
            f"Expected redirect for anonymous bootstrap, got {response.status}"
        )


class TestNoDirectSyncServerCalls:
    """Verify the browser never calls SyncServer directly."""

    def test_no_syncserver_requests_from_browser(
        self, page, django_base_url: str, sync_server_url: str
    ) -> None:
        """All network requests should go through Django, never directly to SyncServer."""
        captured_urls: list[str] = []

        def on_response(resp):
            captured_urls.append(resp.url)

        page.on("response", on_response)

        login(page, TEST_USERNAME, TEST_PASSWORD)
        page.goto(f"{django_base_url}/nomenclature/", wait_until="networkidle")

        # Also wait a moment for any lazy API calls
        page.wait_for_timeout(2000)

        # Build a pattern from the SyncServer base URL
        sync_pattern = re.compile(
            re.escape(sync_server_url.rstrip("/")),
            re.IGNORECASE,
        )

        direct_sync_calls = [
            url for url in captured_urls
            if sync_pattern.search(url)
            and django_base_url.rstrip("/") not in url
        ]

        assert not direct_sync_calls, (
            f"Browser made direct SyncServer calls (security violation):\n"
            + "\n".join(direct_sync_calls)
        )
