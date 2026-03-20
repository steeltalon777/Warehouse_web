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


def _get_sync_binding(user):
    try:
        return getattr(user, "sync_binding", None)
    except (DatabaseError, ObjectDoesNotExist):
        return None


def _get_role(user):
    binding = _get_sync_binding(user)
    if binding is not None and getattr(binding, "sync_role", None):
        return binding.sync_role

    profile = _get_profile(user)
    if profile is not None:
        return profile.role

    return None


def get_user_role(user):
    return _get_role(user)


def has_profile(user):
    return _get_profile(user) is not None


def is_root(user):
    return user.is_superuser or (
        user.is_authenticated and _get_role(user) == "root"
    )


def is_chief_storekeeper(user):
    if user.is_superuser:
        return True
    return user.is_authenticated and _get_role(user) == "chief_storekeeper"


def is_storekeeper(user):
    if user.is_superuser:
        return True
    return user.is_authenticated and _get_role(user) == "storekeeper"


def is_observer(user):
    if user.is_superuser:
        return False
    return user.is_authenticated and _get_role(user) == "observer"


def can_manage_catalog(user):
    return is_root(user) or is_chief_storekeeper(user)


def can_use_client(user):
    return bool(user.is_authenticated and getattr(user, "is_active", False))
