"""
SyncServer authentication integration for Django.

This module provides integration between Django session authentication
and SyncServer identity management. It stores SyncServer identity tokens
in Django session after successful Django login.

Key concepts:
1. Django auth - technical admin/staff layer (username/password)
2. SyncServer auth - domain user identity (tokens, roles, sites)
3. Integration - after Django login, fetch SyncServer identity and store in session

Usage:
    # In Django login view/signal:
    from apps.sync_client.auth_integration import sync_auth_login
    
    sync_auth_login(request, username, password)
    
    # In views/middleware:
    from apps.sync_client.auth_integration import get_sync_identity
    
    identity = get_sync_identity(request)
    if identity:
        print(f"User token: {identity.user_token}")
        print(f"Role: {identity.role}")
        print(f"Site ID: {identity.site_id}")
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.http import HttpRequest

from .auth_api import AuthAPI, get_auth_api
from .exceptions import SyncAPIError

logger = structlog.get_logger()


@dataclass
class SyncIdentity:
    """
    Structured SyncServer identity information.
    
    This dataclass represents the authenticated SyncServer user identity
    stored in Django session after successful login.
    
    Attributes:
        user_token (str): SyncServer user authentication token
        user_id (str): SyncServer user identifier
        role (str): User role in SyncServer (e.g., 'storekeeper', 'chief', 'root')
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
        """
        Get current site ID (alias for default_site_id).
        
        Returns:
            Optional site ID for user operations
        """
        return self.default_site_id
    
    def has_site_access(self, site_id: str) -> bool:
        """
        Check if user has access to specific site.
        
        Args:
            site_id: Site identifier to check
            
        Returns:
            bool: True if user has access to the site
        """
        return any(site.get("id") == site_id for site in self.available_sites)
    
    def get_site_info(self, site_id: str) -> Optional[dict[str, Any]]:
        """
        Get information about specific site.
        
        Args:
            site_id: Site identifier
            
        Returns:
            Optional site information dictionary
        """
        for site in self.available_sites:
            if site.get("id") == site_id:
                return site
        return None


def sync_auth_login(request: HttpRequest, username: str, password: str) -> Optional[SyncIdentity]:
    """
    Perform SyncServer authentication after Django login.
    
    This function should be called after successful Django authentication
    to fetch and store SyncServer identity in the session.
    
    Args:
        request: Django HttpRequest object
        username: Username used for Django login
        password: Password used for Django login
        
    Returns:
        SyncIdentity object if authentication successful, None otherwise
        
    Raises:
        SyncAPIError: If SyncServer API request fails
    """
    logger.info(
        "performing_sync_auth", username=username,
    )
    
    try:
        # Initialize AuthAPI
        auth_api = get_auth_api()
        
        # Sync user registry via SyncServer POST /auth/sync-user (root-only).
        # Response contains user token, id, role, is_root, default_site_id.
        sync_result = auth_api.sync_user(request, {
            "username": username,
            "password": password,
        })
        
        user_data = sync_result.get("user", {})
        user_token = user_data.get("user_token") or user_data.get("token")
        user_id = user_data.get("id", "")
        role = user_data.get("role", "storekeeper")
        is_root = user_data.get("is_root", False)
        default_site_id = user_data.get("default_site_id")
        
        if not user_token:
            logger.error("no_user_token_in_sync_user_response")
            return None
        
        # Store partial identity in session first so subsequent
        # get_context/get_sites calls can use session-based auth.
        identity = SyncIdentity(
            user_token=user_token,
            user_id=user_id,
            role=role,
            is_root=is_root,
            available_sites=[],
            default_site_id=default_site_id,
        )
        _store_identity_in_session(request, identity)
        
        # Now fetch context (sites, current site) with session identity active
        try:
            context = auth_api.get_context(request)
            site = context.get("site", {})
            sites = context.get("sites", [])
            
            identity = SyncIdentity(
                user_token=user_token,
                user_id=user_data.get("id", user_id),
                role=context.get("user", {}).get("role", role),
                is_root=context.get("user", {}).get("is_root", is_root),
                available_sites=sites,
                default_site_id=site.get("id") or default_site_id,
            )
        except Exception as ctx_err:
            logger.warning(
                "failed_to_fetch_sync_context_using_partial", error=str(ctx_err),
            )
            identity = SyncIdentity(
                user_token=user_token,
                user_id=user_id,
                role=role,
                is_root=is_root,
                available_sites=[],
                default_site_id=default_site_id,
            )
        
        # Store final identity in session
        _store_identity_in_session(request, identity)
        
        logger.info(
            "sync_auth_successful",
            user_id=identity.user_id,
            role=identity.role,
            site_id=identity.site_id,
        )
        
        return identity
        
    except SyncAPIError as e:
        logger.error(
            "sync_auth_failed",
            username=username,
            error=str(e),
            status_code=e.status_code,
        )
        raise
    except Exception as e:
        logger.error(
            "unexpected_sync_auth_error", username=username, exc_info=True,
        )
        return None


def sync_auth_login_with_context(request: HttpRequest) -> Optional[SyncIdentity]:
    """
    Alternative login function that only uses get_context().
    
    This function assumes user_token is already in session (e.g., from
    a separate authentication flow) and just fetches the context.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        SyncIdentity object if successful, None otherwise
    """
    logger.info("fetching_sync_context_for_auth")
    
    try:
        # Initialize AuthAPI
        auth_api = get_auth_api()
        
        # Get authentication context
        context = auth_api.get_context(request)
        
        # Extract identity information
        user = context.get("user", {})
        site = context.get("site", {})
        sites = context.get("sites", [])
        
        # Get user token from session
        user_token = request.session.get('user_token')
        if not user_token:
            logger.warning("no_user_token_in_session")
            # Try to get token from context
            user_token = user.get("token")
            if not user_token:
                logger.error("no_user_token_available")
                return None
        
        # Create identity object
        identity = SyncIdentity(
            user_token=user_token,
            user_id=user.get("id", ""),
            role=user.get("role", "storekeeper"),
            is_root=user.get("is_root", False),
            available_sites=sites,
            default_site_id=site.get("id")
        )
        
        # Store identity in session
        _store_identity_in_session(request, identity)
        
        logger.info(
            "sync_context_fetched_successfully",
            user_id=identity.user_id,
            role=identity.role,
            site_id=identity.site_id,
        )
        
        return identity
        
    except SyncAPIError as e:
        logger.error(
            "failed_to_fetch_sync_context",
            error=str(e),
            status_code=e.status_code,
        )
        raise
    except Exception as e:
        logger.error("unexpected_error_fetching_sync_context", exc_info=True)
        return None


def sync_auth_logout(request: HttpRequest) -> None:
    """
    Clear SyncServer identity from session on logout.
    
    Args:
        request: Django HttpRequest object
    """
    logger.debug("clearing_sync_identity_from_session")
    
    # Clear all SyncServer-related session keys
    session_keys = [
        'sync_user_token',
        'sync_user_id', 
        'sync_role',
        'sync_is_root',
        'sync_available_sites',
        'sync_default_site_id',
        'user_token',  # Legacy key used by SyncClient
    ]
    
    for key in session_keys:
        if key in request.session:
            del request.session[key]
    
    logger.info("sync_identity_cleared_from_session")


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
            logger.debug("missing_session_key", key=key)
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
        
        # Also ensure legacy user_token is set for SyncClient compatibility
        if 'user_token' not in request.session:
            request.session['user_token'] = identity.user_token
        
        return identity
        
    except KeyError as e:
        logger.warning("corrupted_sync_identity", error=str(e))
        return None
    except Exception as e:
        logger.error("error_parsing_sync_identity", exc_info=True)
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


def update_sync_site(request: HttpRequest, site_id: str) -> bool:
    """
    Update current site in SyncServer identity.
    
    Args:
        request: Django HttpRequest object
        site_id: New site identifier
        
    Returns:
        bool: True if site was successfully updated
    """
    identity = get_sync_identity(request)
    if not identity:
        logger.warning("cannot_update_site_no_identity")
        return False
    
    # Check if user has access to the new site
    if not identity.has_site_access(site_id):
        logger.warning(
            "user_no_site_access", user_id=identity.user_id, site_id=site_id,
        )
        return False
    
    # Update site in session
    request.session['sync_default_site_id'] = site_id
    
    logger.info(
        "updated_sync_site", user_id=identity.user_id, site_id=site_id,
    )
    
    return True


def _store_identity_in_session(request: HttpRequest, identity: SyncIdentity) -> None:
    """
    Store SyncIdentity object in Django session.
    
    Args:
        request: Django HttpRequest object
        identity: SyncIdentity to store
    """
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
        "stored_sync_identity_in_session",
        user_id=identity.user_id,
        role=identity.role,
        has_site=identity.site_id is not None,
    )


# Context processor for template access
def sync_identity_context(request: HttpRequest) -> dict[str, Any]:
    """
    Django context processor to make Sync identity available in templates.
    
    Add to TEMPLATES.context_processors in settings:
        'apps.sync_client.auth_integration.sync_identity_context'
    
    Usage in templates:
        {% if sync_identity %}
            User: {{ sync_identity.user_id }}
            Role: {{ sync_identity.role }}
            Site: {{ sync_identity.site_id }}
        {% endif %}
    """
    identity = get_sync_identity(request)
    
    return {
        'sync_identity': identity,
        'has_sync_identity': identity is not None,
        'sync_user_role': identity.role if identity else None,
        'sync_site_id': identity.site_id if identity else None,
    }