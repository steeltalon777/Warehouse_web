from django.db import DatabaseError


def is_authenticated_user(user):
    return user.is_authenticated


def _get_profile(user):
    """Return optional legacy profile without breaking admin auth flow.

    In the target architecture Django auth is technical (superuser/staff),
    while domain users/roles/sites are owned by SyncServer. If legacy
    `users_userprofile` table is absent during transition, permissions should
    gracefully fall back instead of crashing.
    """

    try:
        return getattr(user, "profile", None)
    except DatabaseError:
        return None


def has_profile(user):
    return _get_profile(user) is not None


def is_root(user):
    profile = _get_profile(user)
    return user.is_superuser or (
        user.is_authenticated
        and profile is not None
        and profile.role == "root"
    )


def is_chief_storekeeper(user):
    profile = _get_profile(user)
    return (
        user.is_authenticated
        and profile is not None
        and profile.role == "chief_storekeeper"
    )


def is_storekeeper(user):
    profile = _get_profile(user)
    return (
        user.is_authenticated
        and profile is not None
        and profile.role == "storekeeper"
    )


def can_manage_catalog(user):
    return is_root(user) or is_chief_storekeeper(user)


def can_use_client(user):
    profile = _get_profile(user)
    return (
        user.is_authenticated
        and profile is not None
        and profile.is_active
    ) or user.is_superuser
