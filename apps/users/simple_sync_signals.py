"""
Simple SyncServer authentication signals for Django.

This module provides minimal signal handlers that integrate SyncServer
authentication with Django's authentication system without complex logic.

Signals:
    - user_logged_in: Fetch and store SyncServer identity
    - user_logged_out: Clear SyncServer identity from session
"""

import logging
from typing import Any

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.http import HttpRequest

from apps.sync_client.session_auth import (
    store_syncserver_identity,
    clear_syncserver_identity,
)

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def on_user_logged_in(
    sender: Any,
    request: HttpRequest,
    user: Any,
    **kwargs: Any
) -> None:
    """
    Handle Django user login - fetch SyncServer identity.
    
    This signal is triggered after successful Django authentication.
    It fetches SyncServer identity and stores it in the session.
    
    Args:
        sender: The signal sender
        request: Django HttpRequest object
        user: Authenticated Django user object
        **kwargs: Additional signal arguments
    """
    logger.info(
        "Django user logged in, fetching SyncServer identity",
        extra={"username": user.username, "user_id": user.id}
    )
    
    try:
        # Fetch and store SyncServer identity
        identity = store_syncserver_identity(request)
        
        if identity:
            logger.info(
                "SyncServer identity stored after Django login",
                extra={
                    "django_user": user.username,
                    "sync_user_id": identity.user_id,
                    "role": identity.role,
                    "site_id": identity.site_id
                }
            )
        else:
            logger.warning(
                "Failed to fetch SyncServer identity after Django login",
                extra={"django_user": user.username}
            )
            
    except Exception as e:
        logger.exception(
            "Error during SyncServer identity fetch after Django login",
            extra={"username": user.username, "error": str(e)}
        )
        # Don't raise exception - allow Django login to succeed even if
        # SyncServer authentication fails (graceful degradation)


@receiver(user_logged_out)
def on_user_logged_out(
    sender: Any,
    request: HttpRequest,
    user: Any,
    **kwargs: Any
) -> None:
    """
    Handle Django user logout - clear SyncServer identity.
    
    This signal is triggered when a user logs out of Django.
    It clears the SyncServer identity from the session.
    
    Args:
        sender: The signal sender
        request: Django HttpRequest object
        user: The user that was logged out (may be None)
        **kwargs: Additional signal arguments
    """
    username = user.username if user else "unknown"
    logger.info(
        "Django user logged out, clearing SyncServer identity",
        extra={"username": username}
    )
    
    try:
        # Clear SyncServer identity from session
        clear_syncserver_identity(request)
        
        logger.info(
            "SyncServer identity cleared after Django logout",
            extra={"username": username}
        )
        
    except Exception as e:
        logger.exception(
            "Error clearing SyncServer identity after Django logout",
            extra={"username": username}
        )


# Utility function for views
def get_sync_identity_from_request(request: HttpRequest):
    """
    Get SyncServer identity from request.
    
    Convenience function for views to access SyncServer identity.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        SyncIdentity object or None
    """
    from apps.sync_client.session_auth import get_sync_identity
    return get_sync_identity(request)


# Context processor
def sync_identity_context(request: HttpRequest) -> dict:
    """
    Django context processor to make Sync identity available in templates.
    
    Add to TEMPLATES.context_processors in settings:
        'apps.users.simple_sync_signals.sync_identity_context'
    
    Usage in templates:
        {% if sync_identity %}
            User: {{ sync_identity.user_id }}
            Role: {{ sync_identity.role }}
            Site: {{ sync_identity.site_id }}
        {% endif %}
    """
    from apps.sync_client.session_auth import get_sync_identity
    identity = get_sync_identity(request)
    
    return {
        'sync_identity': identity,
        'has_sync_identity': identity is not None,
    }