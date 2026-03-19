from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]

# Explicit environment file support for container/runtime wiring.
ENV_FILE = os.getenv("DJANGO_ENV_FILE", str(BASE_DIR / ".env"))
load_dotenv(ENV_FILE)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["127.0.0.1", "localhost"] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", [])

# Django auth in this project is a technical admin/staff layer.
# Warehouse domain users/roles/sites are owned by SyncServer.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.users",
    "apps.catalog",
    "apps.client",
    "apps.documents",
    "apps.common",
    "apps.sync_client",
    "apps.operations",
    "apps.balances",
    "apps.admin_panel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.getenv("DB_NAME", str(BASE_DIR / "db.sqlite3")),
        "USER": os.getenv("DB_USER", ""),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", ""),
        "PORT": os.getenv("DB_PORT", ""),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Asia/Yakutsk"
USE_I18N = True
USE_TZ = True

LOGIN_URL = "/users/login/"
LOGIN_REDIRECT_URL = "/client/"
LOGOUT_REDIRECT_URL = "/users/login/"

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -------------------------------------------------------------------
# SyncServer integration (canonical)
# -------------------------------------------------------------------
# IMPORTANT:
# - Django SSR client must talk only to versioned SyncServer API.
# - Base URL MUST already include /api/v1
# - Web client uses service-auth only.
SYNC_SERVER_URL = os.getenv("SYNC_SERVER_URL", "http://syncserver:8000/api/v1").rstrip("/")
SYNC_SERVER_SERVICE_TOKEN = os.getenv("SYNC_SERVER_SERVICE_TOKEN", "").strip()
SYNC_ROOT_USER_TOKEN = os.getenv("SYNC_ROOT_USER_TOKEN", "").strip()
SYNC_SERVER_TIMEOUT = float(os.getenv("SYNC_SERVER_TIMEOUT", "10"))

# Optional default acting context for technical/service flows.
# Business requests should normally pass explicit acting context from app layer.
SYNC_DEFAULT_ACTING_USER_ID = os.getenv("SYNC_DEFAULT_ACTING_USER_ID", "").strip()
SYNC_DEFAULT_ACTING_SITE_ID = os.getenv("SYNC_DEFAULT_ACTING_SITE_ID", "").strip()

# -------------------------------------------------------------------
# Legacy device-auth settings
# -------------------------------------------------------------------
# DEPRECATED:
# Django web client MUST NOT use device auth for business/admin operations.
# Left here only to avoid hard crash in unrelated old code during migration.
SYNC_SITE_ID = os.getenv("SYNC_SITE_ID", "").strip()
SYNC_DEVICE_ID = os.getenv("SYNC_DEVICE_ID", "").strip()
SYNC_DEVICE_TOKEN = os.getenv("SYNC_DEVICE_TOKEN", "").strip()
SYNC_CLIENT_VERSION = os.getenv("SYNC_CLIENT_VERSION", "warehouse-web/1.0").strip()

# Legacy alias support (read-only fallback). Do not use in new code.
SYNCSERVER_API_URL = SYNC_SERVER_URL

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/client/"
LOGOUT_REDIRECT_URL = "/login/"
SYNC_WEB_DEVICE_ID = os.getenv("SYNC_WEB_DEVICE_ID", "00000000-0000-0000-0000-000000000001").strip()
