from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import Client


def main() -> None:
    user_model = get_user_model()
    user, _created = user_model.objects.get_or_create(
        username="bff_smoke",
        defaults={
            "email": "bff_smoke@example.local",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.set_password("bff-smoke-pass-123")
    user.save()

    client = Client(HTTP_HOST="localhost")
    login_ok = client.login(username="bff_smoke", password="bff-smoke-pass-123")

    session = client.session
    session["sync_user_token"] = settings.SYNC_ROOT_USER_TOKEN
    session.save()

    paths = [
        "/bff/api/v1/health",
        "/bff/api/v1/auth/me",
        "/bff/api/v1/catalog/items?limit=1",
        "/bff/api/v1/operations?page=1&page_size=1",
        "/bff/api/v1/balances?page=1&page_size=1",
        "/bff/api/v1/reports/stock-summary?page=1&page_size=1",
    ]

    print(f"LOGIN {login_ok}")
    for path in paths:
        response = client.get(path)
        try:
            payload = response.json()
            ok = payload.get("ok")
            print(f"{path} status={response.status_code} ok={ok}")
        except Exception:
            print(f"{path} status={response.status_code} non_json")


if __name__ == "__main__":
    main()
