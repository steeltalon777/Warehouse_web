def is_authenticated_user(user):
    return user.is_authenticated


def has_profile(user):
    return hasattr(user, "profile")


def is_root(user):
    return user.is_superuser or (
        user.is_authenticated
        and hasattr(user, "profile")
        and user.profile.role == "root"
    )


def is_chief_storekeeper(user):
    return (
        user.is_authenticated
        and hasattr(user, "profile")
        and user.profile.role == "chief_storekeeper"
    )


def is_storekeeper(user):
    return (
        user.is_authenticated
        and hasattr(user, "profile")
        and user.profile.role == "storekeeper"
    )


def can_manage_catalog(user):
    return is_root(user) or is_chief_storekeeper(user)


def can_use_client(user):
    return (
        user.is_authenticated
        and hasattr(user, "profile")
        and user.profile.is_active
    ) or user.is_superuser