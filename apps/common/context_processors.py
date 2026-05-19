from django.conf import settings

from apps.sync_client.session_auth import get_sync_identity

_ROLE_LABELS = {
    "root": "Root",
    "chief_storekeeper": "Главный кладовщик",
    "storekeeper": "Кладовщик",
    "observer": "Обозреватель",
}


def _get_role_label(role: str) -> str:
    return _ROLE_LABELS.get(role, role.capitalize())


def shell_context(request):
    return {
        "organization_short_name": settings.ORGANIZATION_SHORT_NAME,
        "organization_full_name": settings.ORGANIZATION_FULL_NAME,
        "organization_logo_static_path": getattr(settings, "ORGANIZATION_LOGO_STATIC_PATH", "img/logo.png"),
    }


def sync_identity_context(request):
    identity = get_sync_identity(request) if request.user.is_authenticated else None
    if identity is not None:
        return {
            "sync_role": identity.role,
            "sync_role_label": _get_role_label(identity.role),
            "has_sync_identity": True,
        }
    return {
        "sync_role": None,
        "sync_role_label": None,
        "has_sync_identity": False,
    }
