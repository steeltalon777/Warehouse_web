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

# -------------------------------------------------------------------
# Global organization identity
# -------------------------------------------------------------------
ORGANIZATION_FULL_NAME = os.getenv(
    "ORGANIZATION_FULL_NAME",
    'Общество с ограниченной ответственностью Автоматизированные системы "Горизонт"',
).strip()
ORGANIZATION_SHORT_NAME = os.getenv("ORGANIZATION_SHORT_NAME", 'ООО АС "Горизонт"').strip()

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
    "apps.catalog_cache",
    "apps.client",
    "apps.documents",
    "apps.common",
    "apps.sync_client",
    "apps.operations",
    "apps.balances",
    "apps.admin_panel",
    "apps.temporary_items",
    "apps.bff_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestTracingMiddleware",
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
                "apps.common.context_processors.shell_context",
                "apps.common.context_processors.sync_identity_context",
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
# Cache policy for BFF transport acceleration
# -------------------------------------------------------------------
# Allowed:
#   - catalog read/search responses
#   - units/categories/sites lookups
#   - navigation/sidebar permission summaries
#   - dashboard counters with short TTL
#   - screen bootstrap bundles
# Forbidden:
#   - raw user/device tokens
#   - SyncServer root token
#   - uncommitted operation write decisions
#   - final authority for balances, access rights, or operation submission
# Cache key MUST include user role / site scope where permissions affect results.
# -------------------------------------------------------------------
_CACHE_BACKEND = os.getenv("DJANGO_CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache")
_CACHE_LOCATION = os.getenv("DJANGO_CACHE_LOCATION", "bff_transport_cache")
CACHES = {
    "default": {
        "BACKEND": _CACHE_BACKEND,
        "LOCATION": _CACHE_LOCATION,
    },
}
# Standard TTLs (seconds) for cache decorators in BFF views.
CACHE_TTL_SHORT = int(os.getenv("CACHE_TTL_SHORT", "30"))       # dashboard counters
CACHE_TTL_MEDIUM = int(os.getenv("CACHE_TTL_MEDIUM", "120"))    # catalog lookups
CACHE_TTL_LONG = int(os.getenv("CACHE_TTL_LONG", "600"))        # reference data (units, sites)

# -------------------------------------------------------------------
# SyncServer integration (canonical)
# -------------------------------------------------------------------
# IMPORTANT:
# - Django SSR client must talk only to versioned SyncServer API.
# - Base URL MUST already include /api/v1
# - Transport uses only X-User-Token and X-Device-Token headers.
SYNC_SERVER_URL = os.getenv("SYNC_SERVER_URL", "http://syncserver:8000/api/v1").rstrip("/")
SYNC_ROOT_USER_TOKEN = os.getenv("SYNC_ROOT_USER_TOKEN", "").strip()
SYNC_SERVER_TIMEOUT = float(os.getenv("SYNC_SERVER_TIMEOUT", "10"))

# Fine-grained timeouts for SyncServer HTTP transport.
# Each value is parsed as float seconds; falls back to SYNC_SERVER_TIMEOUT if not set.
_SYNC_FALLBACK = os.getenv("SYNC_SERVER_TIMEOUT", "10")
SYNC_SERVER_CONNECT_TIMEOUT = float(os.getenv("SYNC_SERVER_CONNECT_TIMEOUT", _SYNC_FALLBACK))
SYNC_SERVER_READ_TIMEOUT = float(os.getenv("SYNC_SERVER_READ_TIMEOUT", _SYNC_FALLBACK))
SYNC_SERVER_WRITE_TIMEOUT = float(os.getenv("SYNC_SERVER_WRITE_TIMEOUT", _SYNC_FALLBACK))
SYNC_SERVER_POOL_TIMEOUT = float(os.getenv("SYNC_SERVER_POOL_TIMEOUT", _SYNC_FALLBACK))

# Retry policy for idempotent SyncServer requests (GET, health).
# Applied only to safe reads; mutations are never retried without idempotency key.
SYNC_SERVER_RETRIES = int(os.getenv("SYNC_SERVER_RETRIES", "2"))
SYNC_SERVER_RETRY_BACKOFF = float(os.getenv("SYNC_SERVER_RETRY_BACKOFF", "0.2"))

# Optional device-token for audit context (not for ordinary auth).
SYNC_DEVICE_TOKEN = os.getenv("SYNC_DEVICE_TOKEN", "").strip()

# -------------------------------------------------------------------
# HISTORICAL — removed from active use
# -------------------------------------------------------------------
# The following settings were used by the old multi-header auth model
# (service tokens, acting context headers, legacy device auth).
# They are retained here only as env-var references for backward
# compat during transition. Active code must not read them.
#
# Removed: SYNC_SERVER_SERVICE_TOKEN, SYNC_DEFAULT_ACTING_USER_ID,
#          SYNC_DEFAULT_ACTING_SITE_ID, SYNC_SITE_ID, SYNC_DEVICE_ID,
#          SYNC_CLIENT_VERSION, SYNCSERVER_API_URL, SYNC_WEB_DEVICE_ID.

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/client/"
LOGOUT_REDIRECT_URL = "/login/"

# -------------------------------------------------------------------
# Frontend SPA integration
# -------------------------------------------------------------------
# FRONTEND_MODE: "dev" (Angular dev server at :4200 with proxy) or "build" (Django serves built files)
FRONTEND_MODE = os.getenv("FRONTEND_MODE", "build").strip()
FRONTEND_DEV_SERVER_URL = os.getenv("FRONTEND_DEV_SERVER_URL", "http://localhost:4200").strip()
FRONTEND_BUILD_DIR = os.getenv(
    "FRONTEND_BUILD_DIR",
    str(BASE_DIR.parent / "Warehouse_frontend" / "dist" / "warehouse-frontend" / "browser"),
).strip()
