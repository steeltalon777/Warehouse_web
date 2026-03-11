import os

_environment = os.getenv("DJANGO_ENV", "development").lower()

if _environment == "production":
    from .production import *  # noqa: F401,F403
else:
    from .development import *  # noqa: F401,F403
