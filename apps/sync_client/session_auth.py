"""
SyncServer authentication integration with Django session.

This module provides direct integration between Django authentication
and SyncServer identity management. After Django login, it fetches
SyncServer identity via auth_api.get_context() and stores it in session.

Requirements met:
1. After Django login: call auth_api.get_context()
2. Store in session:
   - sync_user_token
   - sync_user_id
   - sync_role
   - sync_is_root
   - sync_available_sites
   - sync_default_site_id
3. Ensure SyncClient can access session token
4. Add helper: get_sync_identity(request)
5. Do NOT rewrite Django auth system
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from django.conf import settings
from django.http import HttpRequest

from .auth_api import AuthAPI, get_auth_api
from .exceptions import SyncAPIError

logger = logging.getLogger(__name__)


@dataclass
class SyncIdentity:
    """
    Structured SyncServer identity information.
    
    Represents authenticated SyncServer user identity stored in Django session.
    
    Attributes:
        user_token (str): SyncServer user authentication token
        user_id (str): SyncServer user identifier
        role (str): User role (e.g., 'storekeeper', 'chief', 'root')
        is_root (bool): Whether user has root/admin privileges
        available_sites (list[dict]): List of sites user has access to
        default_site_id (Optional[str]): Default site ID for user operations
    """
    user_token: str
    user_id: str
    role: str
    is_root: bool
    available_sites: list[dict[str, Any]]
    default_site_id: Optional[str] = None
    
    @property
    def site_id(self) -> Optional[str]:
        """Get current site ID (alias for default_site_id)."""
        return self.default_site_id


def store_syncserver_identity(request: HttpRequest) -> Optional[SyncIdentity]:
    """
    Fetch SyncServer identity and store it in Django session.
    
    This function should be called after successful Django login.
    It calls auth_api.get_context() and stores the identity in session.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        SyncIdentity object if successful, None otherwise
    """
    logger.info("Fetching SyncServer identity for Django session")
    
    try:
        # Initialize AuthAPI
        auth_api = get_auth_api()
        
        # Get authentication context from SyncServer
        context = auth_api.get_context(request)
        
        # Extract identity information from the current SyncServer schema,
        # while remaining tolerant of older key names.
        user = context.get("user", {})
        default_site = context.get("default_site") or context.get("site") or {}
        available_sites = [
            _normalize_sync_site(site)
            for site in (context.get("available_sites") or context.get("sites") or [])
        ]

        user_token = _resolve_sync_user_token(request, context, user)

        if not user_token:
            logger.error("No user token found in SyncServer context")
            return None
        
        # Create identity object
        identity = SyncIdentity(
            user_token=user_token,
            user_id=user.get("id", ""),
            role=context.get("role") or user.get("role", "storekeeper"),
            is_root=bool(context.get("is_root", user.get("is_root", False))),
            available_sites=available_sites,
            default_site_id=default_site.get("site_id") or default_site.get("id")
        )
        
        # Store identity in session
        _store_identity_in_session(request, identity)
        
        logger.info(
            "SyncServer identity stored in session",
            extra={
                "user_id": identity.user_id,
                "role": identity.role,
                "site_id": identity.site_id,
                "available_sites": len(identity.available_sites)
            }
        )
        
        return identity
        
    except SyncAPIError as e:
        logger.error(
            "Failed to fetch SyncServer identity",
            extra={
                "error": str(e),
                "status_code": e.status_code
            }
        )
        return None
    except Exception as e:
        logger.exception("Unexpected error fetching SyncServer identity")
        return None


def clear_syncserver_identity(request: HttpRequest) -> None:
    """
    Clear SyncServer identity from Django session.
    
    This function should be called on Django logout.
    
    Args:
        request: Django HttpRequest object
    """
    logger.debug("Clearing SyncServer identity from session")
    
    # Clear all SyncServer-related session keys
    session_keys = [
        'sync_user_token',
        'sync_user_id', 
        'sync_role',
        'sync_is_root',
        'sync_available_sites',
        'sync_default_site_id',
        'user_token',  # Legacy key for SyncClient compatibility
    ]
    
    for key in session_keys:
        if key in request.session:
            del request.session[key]
    
    logger.info("SyncServer identity cleared from session")


def get_sync_identity(request: HttpRequest) -> Optional[SyncIdentity]:
    """
    Get SyncServer identity from Django session.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        SyncIdentity object if identity exists in session, None otherwise
    """
    # Check if all required session keys exist
    required_keys = [
        'sync_user_token',
        'sync_user_id',
        'sync_role',
        'sync_is_root',
        'sync_available_sites',
    ]
    
    for key in required_keys:
        if key not in request.session:
            logger.debug(f"Missing session key for Sync identity: {key}")
            return None
    
    try:
        identity = SyncIdentity(
            user_token=request.session['sync_user_token'],
            user_id=request.session['sync_user_id'],
            role=request.session['sync_role'],
            is_root=request.session['sync_is_root'],
            available_sites=request.session['sync_available_sites'],
            default_site_id=request.session.get('sync_default_site_id')
        )
        
        # Ensure legacy user_token is set for SyncClient compatibility
        if 'user_token' not in request.session:
            request.session['user_token'] = identity.user_token
        
        return identity
        
    except KeyError as e:
        logger.warning(f"Corrupted Sync identity in session: {e}")
        return None
    except Exception as e:
        logger.exception("Error parsing Sync identity from session")
        return None


def has_sync_identity(request: HttpRequest) -> bool:
    """
    Check if SyncServer identity exists in session.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        bool: True if Sync identity exists in session
    """
    return get_sync_identity(request) is not None


def _store_identity_in_session(request: HttpRequest, identity: SyncIdentity) -> None:
    """
    Store SyncIdentity object in Django session.
    
    Args:
        request: Django HttpRequest object
        identity: SyncIdentity to store
    """
    # Store all identity fields in session
    request.session['sync_user_token'] = identity.user_token
    request.session['sync_user_id'] = identity.user_id
    request.session['sync_role'] = identity.role
    request.session['sync_is_root'] = identity.is_root
    request.session['sync_available_sites'] = identity.available_sites
    request.session['sync_default_site_id'] = identity.default_site_id
    
    # Also set legacy user_token for SyncClient compatibility
    request.session['user_token'] = identity.user_token
    
    # Mark session as modified
    request.session.modified = True
    
    logger.debug(
        "Stored Sync identity in session",
        extra={
            "user_id": identity.user_id,
            "role": identity.role,
            "has_site": identity.site_id is not None
        }
    )


def _resolve_sync_user_token(
    request: HttpRequest,
    context: dict[str, Any],
    user: dict[str, Any],
) -> str:
    session = getattr(request, "session", None)

    token_candidates = [
        user.get("user_token"),
        user.get("token"),
        context.get("token"),
        session.get("sync_user_token") if session is not None else None,
        session.get("user_token") if session is not None else None,
    ]
    for candidate in token_candidates:
        if candidate not in (None, ""):
            logger.debug("Resolved SyncServer token from context/session")
            return str(candidate)

    request_user = getattr(request, "user", None)
    if request_user is None or not getattr(request_user, "is_authenticated", False):
        return ""

    if getattr(request_user, "is_superuser", False):
        token = getattr(settings, "SYNC_ROOT_USER_TOKEN", "").strip()
        if token:
            logger.debug("Resolved SyncServer token from root user fallback")
        return token

    try:
        token = str(request_user.sync_binding.sync_user_token or "").strip()
    except Exception:
        token = ""

    if token:
        logger.debug("Resolved SyncServer token from sync binding fallback")

    return token


def _normalize_sync_site(site: dict[str, Any]) -> dict[str, Any]:
    return {
        **site,
        "id": site.get("id", site.get("site_id")),
    }


# Simple signal handlers for direct integration
def handle_django_login(request: HttpRequest) -> None:
    """
    Handle Django login - fetch and store SyncServer identity.
    
    Call this function directly from Django login view or signal.
    
    Args:
        request: Django HttpRequest object
    """
    if request.user.is_authenticated:
        identity = store_syncserver_identity(request)
        if identity:
            logger.info(
                "SyncServer identity stored after Django login",
                extra={
                    "django_user": request.user.username,
                    "sync_user_id": identity.user_id,
                    "role": identity.role
                }
            )
        else:
            logger.warning(
                "Failed to store SyncServer identity after Django login",
                extra={"django_user": request.user.username}
            )


def handle_django_logout(request: HttpRequest) -> None:
    """
    Handle Django logout - clear SyncServer identity.
    
    Call this function directly from Django logout view or signal.
    
    Args:
        request: Django HttpRequest object
    """
    clear_syncserver_identity(request)
    logger.info(
        "SyncServer identity cleared after Django logout",
        extra={"user": request.user.username if request.user.is_authenticated else "unknown"}
    )
