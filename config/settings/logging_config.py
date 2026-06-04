"""
structlog configuration for Warehouse_web (Django).

Must be called from settings/base.py via:

    from config.settings.logging_config import LOGGING

Then Django reads settings.LOGGING and applies it automatically.
"""

import os


def _build_structlog_formatter(log_format: str):
    """Return a logging formatter config dict for structlog + chosen renderer.

    Returns a complete ``ProcessorFormatter`` config dict suitable for direct
    use in Django's ``LOGGING["formatters"]`` dict (no extra ``"()":`` wrapping).

    Example usage::

        LOGGING = {
            "formatters": {
                "structlog_console": _build_structlog_formatter("console"),
            },
            ...
        }
    """
    import structlog

    if log_format == "json":
        processor = structlog.processors.JSONRenderer()
    else:
        processor = structlog.dev.ConsoleRenderer(colors=True, pad_event=40)

    return {
        "()": structlog.stdlib.ProcessorFormatter,
        "processor": processor,
        "foreign_pre_chain": [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.PositionalArgumentsFormatter(),
        ],
    }


_LOG_FORMAT = os.getenv("LOG_FORMAT", "console").strip().lower()
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structlog_console": _build_structlog_formatter("console"),
        "structlog_json": _build_structlog_formatter("json"),
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": f"structlog_{_LOG_FORMAT}" if _LOG_FORMAT in ("console", "json") else "structlog_console",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": _LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        # Shut up noisy third parties in dev
        "httpx": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "httpcore": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}


def configure_structlog():
    """Call once at Django startup to wire structlog globally.

    Must be called from AppConfig.ready() or settings after LOGGING is applied.
    """
    import structlog

    log_format = _LOG_FORMAT

    if log_format == "json":
        renderer_processor = structlog.processors.JSONRenderer()
    else:
        renderer_processor = structlog.dev.ConsoleRenderer(colors=True, pad_event_to=40)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
