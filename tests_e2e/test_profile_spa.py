"""
Playwright smoke tests for the User Profile Self-Service page.

Run with:
    cd Warehouse_web && python tests_e2e/test_profile_spa.py
"""

import sys
from playwright.sync_api import sync_playwright, BrowserContext, Page

DJANGO_BASE_URL = "http://localhost:8001"
TEST_USERNAME = "test_profile"
TEST_PASSWORD = "TestPass123"


def do_login(page: Page):
    """Log in to the application (expects a fresh page/context)."""
    page.goto(f"{DJANGO_BASE_URL}/users/login/", wait_until="networkidle")
    page.fill("input[name=username]", TEST_USERNAME)
    page.fill("input[name=password]", TEST_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle", timeout=10000)
    # Should now be logged in and redirected away from login page


def test_profile_page_loads(context: BrowserContext):
    """Authenticated user can access profile page."""
    page = context.new_page()
    do_login(page)
    page.goto(f"{DJANGO_BASE_URL}/users/profile/", wait_until="networkidle")
    h1 = page.locator("h1").text_content()
    assert "Профиль:" in h1, f"Expected 'Профиль:', got '{h1}'"
    print(f"  ✅ Profile page loads with heading: {h1}")
    page.close()


def test_navbar_profile_link(context: BrowserContext):
    """Navbar username links to profile page."""
    page = context.new_page()
    do_login(page)
    page.goto(f"{DJANGO_BASE_URL}/users/profile/", wait_until="networkidle")

    link = page.locator("a.profile-link")
    assert link.count() > 0, "No .profile-link found"
    href = link.get_attribute("href")
    assert href == "/users/profile/", f"Expected /users/profile/, got {href}"
    print(f"  ✅ Navbar profile link found: {href}")
    page.close()


def test_wrong_current_password(context: BrowserContext):
    """Wrong current password shows validation error."""
    page = context.new_page()
    do_login(page)
    page.goto(f"{DJANGO_BASE_URL}/users/profile/", wait_until="networkidle")

    # Fill form with WRONG current password
    page.fill("#id_current_password", "WrongPassword")
    page.fill("#id_full_name", "Should Not Change")

    # Click save button (not the logout button)
    page.locator("button.btn-primary").click()
    page.wait_for_load_state("networkidle", timeout=10000)

    body_text = page.locator("body").text_content()
    assert "Неверный текущий пароль" in body_text, \
        f"No error message. Body: {body_text[:200]}"
    print("  ✅ Wrong password error message shown")
    page.close()


def test_password_change(context: BrowserContext):
    """Password change then login with new password."""
    page = context.new_page()
    do_login(page)
    page.goto(f"{DJANGO_BASE_URL}/users/profile/", wait_until="networkidle")

    # Fill form with new password
    page.fill("#id_current_password", TEST_PASSWORD)
    page.fill("#id_new_password", "NewPlaywright789")
    page.fill("#id_new_password_confirm", "NewPlaywright789")
    page.fill("#id_full_name", "Playwright User")
    page.fill("#id_email", "pw@test.com")

    # Click save button
    page.locator("button.btn-primary").click()
    page.wait_for_load_state("networkidle", timeout=10000)

    body_after_change = page.locator("body").text_content()
    assert "Данные сохранены" in body_after_change, \
        f"No success after change. Body: {body_after_change[:200]}"
    print("  ✅ Password change submitted successfully")
    page.close()

    # Verify new password: log out by clearing cookies, then login with new password
    # Create a new page — the existing context still has session cookies, so navigate
    # to logout first, then login with new password
    page2 = context.new_page()
    page2.goto(f"{DJANGO_BASE_URL}/users/logout/", wait_until="networkidle")
    page2.goto(f"{DJANGO_BASE_URL}/users/login/", wait_until="networkidle")
    page2.fill("input[name=username]", TEST_USERNAME)
    page2.fill("input[name=password]", "NewPlaywright789")
    page2.click("button[type=submit]")
    page2.wait_for_load_state("networkidle", timeout=10000)

    # Now try to access profile
    page2.goto(f"{DJANGO_BASE_URL}/users/profile/", wait_until="networkidle")

    page2.wait_for_timeout(1000)  # Let page render
    body_text = page2.locator("body").text_content()
    assert "Профиль:" in body_text, \
        f"Could not access profile with new password. Body: {body_text[:200]}"
    print("  ✅ Can access profile after login with new password")

    # Reset password back to original
    page2.fill("#id_current_password", "NewPlaywright789")
    page2.fill("#id_new_password", TEST_PASSWORD)
    page2.fill("#id_new_password_confirm", TEST_PASSWORD)
    page2.fill("#id_full_name", "Playwright User")
    page2.fill("#id_email", "pw@test.com")
    page2.locator("button.btn-primary").click()
    page2.wait_for_load_state("networkidle", timeout=10000)

    body_after_reset = page2.locator("body").text_content()
    assert "Данные сохранены" in body_after_reset, \
        f"No success after reset. Body: {body_after_reset[:200]}"
    print("  ✅ Password reset back to original")
    page2.close()


def run_all():
    failures = 0
    total = 4

    print("\n=== Playwright Profile Tests ===\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Use a FRESH context for each test to avoid shared session cookies
        # Use a fresh context per test
        test_wrappers = [
            ("Profile page loads", test_profile_page_loads),
            ("Navbar profile link", test_navbar_profile_link),
            ("Wrong current password", test_wrong_current_password),
            ("Password change + login with new pwd", test_password_change),
        ]

        for name, test_fn in test_wrappers:
            context = browser.new_context(ignore_https_errors=True)
            try:
                test_fn(context)
                print(f"  ✅ {name} PASSED\n")
            except Exception as e:
                print(f"  ❌ {name} FAILED: {e}\n")
                failures += 1
            try:
                context.close()
            except Exception:
                pass

        browser.close()

    print(f"=== Results: {total - failures}/{total} passed ===")
    return failures


if __name__ == "__main__":
    sys.exit(run_all())
