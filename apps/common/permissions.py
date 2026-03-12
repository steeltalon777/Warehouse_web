from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError


def is_authenticated_user(user):
    return user.is_authenticated


def _get_profile(user):
    """Return optional legacy profile without breaking admin auth flow."""

    try:
        return getattr(user, "profile", None)
    except (DatabaseError, ObjectDoesNotExist):
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
    if user.is_superuser:
        return True
    profile = _get_profile(user)
    return (
        user.is_authenticated
        and profile is not None
        and profile.role == "chief_storekeeper"
    )


def is_storekeeper(user):
    if user.is_superuser:
        return True
    profile = _get_profile(user)
    return (
        user.is_authenticated
        and profile is not None
        and profile.role == "storekeeper"
    )


def can_manage_catalog(user):
    return is_root(user) or is_chief_storekeeper(user)


def can_use_client(user):
    if user.is_superuser:
        return True
    profile = _get_profile(user)
    return (
        user.is_authenticated
        and profile is not None
        and profile.is_active
    )