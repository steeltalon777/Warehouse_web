"""
SyncServer authentication signals for Django.

This module provides signals that integrate SyncServer authentication
with Django's authentication system. It automatically performs SyncServer
authentication after successful Django login and clears SyncServer identity
on logout.

Signals:
    - user_logged_in: Trigger SyncServer authentication
    - user_logged_out: Clear SyncServer identity from session

Usage:
    Import this module in apps.py to register signals automatically.
"""

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.http import HttpRequest

from apps.sync_client.auth_integration import (
    sync_auth_login,
    sync_auth_login_with_context,
    sync_auth_logout,
    get_sync_identity,
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
    Handle Django user login - perform SyncServer authentication.
    
    This signal is triggered after successful Django authentication.
    It attempts to authenticate with SyncServer and store the identity
    in the Django session.
    
    Args:
        sender: The signal sender
        request: Django HttpRequest object
        user: Authenticated Django user object
        **kwargs: Additional signal arguments
    """
    logger.info(
        "Django user logged in, attempting SyncServer authentication",
        extra={"username": user.username, "user_id": user.id}
    )
    
    # Get password from request (available in login view)
    # Note: This assumes password is stored in request.POST during login
    password = request.POST.get('password') if request.method == 'POST' else None
    
    try:
        if password:
            # Try full authentication with credentials
        identity = sync_auth_login(request, user.username, password)
        else:
            # Try to get context with existing session token
            identity = sync_auth_login_with_context(request)

        if identity:
            logger.info(
                "SyncServer authentication successful after Django login",
                extra={
                    "django_user": user.username,
                    "sync_user_id": identity.user_id,
                    "role": identity.role,
                    "site_id": identity.site_id
                }
            )
        else:
            logger.warning(
                "SyncServer authentication failed (no identity returned)",
                extra={"django_user": user.username}
        )

    except Exception as e:
        logger.exception(
            "Error during SyncServer authentication after Django login",
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
        sync_auth_logout(request)
        
        logger.info(
            "SyncServer identity cleared after Django logout",
            extra={"username": username}
        )
        
    except Exception as e:
        logger.exception(
            "Error clearing SyncServer identity after Django logout",
            extra={"username": username}
        )


def check_sync_authentication(request: HttpRequest) -> bool:
    """
    Check if SyncServer authentication is valid.
    
    This function can be used as a decorator or middleware to ensure
    SyncServer identity is present and valid before accessing protected views.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        bool: True if SyncServer identity exists and appears valid
    """
    identity = get_sync_identity(request)
    
    if not identity:
        logger.debug("No SyncServer identity found in session")
                return False
        
    # Check if identity has minimum required fields
    if not identity.user_token or not identity.user_id:
        logger.warning(
            "Invalid SyncServer identity in session",
            extra={"has_token": bool(identity.user_token), "has_user_id": bool(identity.user_id)}
        )
        return False
    
    return True


# Middleware for SyncServer authentication validation
class SyncAuthMiddleware:
    """
    Middleware to validate SyncServer authentication on each request.
    
    This middleware can be added to Django's MIDDLEWARE setting to
    automatically validate SyncServer identity on each request and
    add it to the request object for easy access.
    
    Usage in settings.py:
        MIDDLEWARE = [
            ...
            'apps.users.sync_signals.SyncAuthMiddleware',
            ...
        ]
    
    Then in views:
        sync_identity = request.sync_identity
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Add Sync identity to request object
        request.sync_identity = get_sync_identity(request)
        request.has_sync_identity = request.sync_identity is not None
        
        # Check authentication for protected paths
        if self._requires_sync_auth(request):
            if not request.has_sync_identity:
                logger.warning(
                    "SyncServer authentication required but not found",
                    extra={"path": request.path, "user": request.user.username if request.user.is_authenticated else "anonymous"}
                )
                # Could redirect to login or return 403 here
        
        response = self.get_response(request)
        return response
    
    def _requires_sync_auth(self, request) -> bool:
        """
        Determine if the requested path requires SyncServer authentication.
        
        Args:
            request: Django HttpRequest object
            
        Returns:
            bool: True if path requires SyncServer authentication
        """
        # Paths that don't require SyncServer auth
        exempt_paths = [
            '/users/login/',
            '/users/logout/',
            '/admin/',
            '/static/',
            '/media/',
        ]
        
        path = request.path
        
        # Check if path is exempt
        for exempt in exempt_paths:
            if path.startswith(exempt):
                return False
        
        # Require Sync auth for all other authenticated requests
        return request.user.is_authenticated