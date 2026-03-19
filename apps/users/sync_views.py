"""
SyncServer authentication views for Django.

This module provides views for managing SyncServer authentication state,
such as switching between available sites.

Views:
    - sync_site_switch: Switch current SyncServer site
    - sync_identity_info: View current SyncServer identity information
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.sync_client.auth_integration import (
    get_sync_identity,
    update_sync_site,
    has_sync_identity,
)

logger = logging.getLogger(__name__)


@login_required
def sync_site_switch(request: HttpRequest) -> HttpResponse:
    """
    View for switching between available SyncServer sites.
    
    GET: Show site selection form
    POST: Switch to selected site
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        HttpResponse with site selection or redirect
    """
    identity = get_sync_identity(request)
    
    if not identity:
        # No Sync identity - redirect to login or show error
        logger.warning("Attempt to switch site without Sync identity")
        return render(request, 'sync_auth/error.html', {
            'error': 'SyncServer identity not found. Please log in again.'
        })
    
    if request.method == 'POST':
        site_id = request.POST.get('site_id')
        
        if not site_id:
            return render(request, 'sync_auth/site_switch.html', {
                'identity': identity,
                'error': 'Please select a site.'
            })
        
        # Update site in session
        if update_sync_site(request, site_id):
            logger.info(
                "User switched SyncServer site",
                extra={
                    'user_id': identity.user_id,
                    'old_site_id': identity.site_id,
                    'new_site_id': site_id
                }
            )
            
            # Redirect back to referring page or dashboard
            redirect_to = request.GET.get('next', reverse('client:dashboard'))
            return redirect(redirect_to)
        else:
            return render(request, 'sync_auth/site_switch.html', {
                'identity': identity,
                'error': f'You do not have access to site {site_id}.'
            })
    
    # GET request - show site selection
    return render(request, 'sync_auth/site_switch.html', {
        'identity': identity,
        'next': request.GET.get('next', '')
    })


@login_required
def sync_identity_info(request: HttpRequest) -> HttpResponse:
    """
    View current SyncServer identity information.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        HttpResponse with identity information
    """
    identity = get_sync_identity(request)
    
    if not identity:
        return render(request, 'sync_auth/error.html', {
            'error': 'No SyncServer identity found. Please log in again.'
        })
    
    return render(request, 'sync_auth/identity_info.html', {
        'identity': identity,
    })


@login_required
@require_POST
def sync_refresh_identity(request: HttpRequest) -> HttpResponse:
    """
    Refresh SyncServer identity from API.
    
    This view forces a refresh of the SyncServer identity by
    re-authenticating with SyncServer. Useful if identity information
    has become stale or needs to be updated.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        HttpResponseRedirect to referring page
    """
    # Note: This would require storing credentials securely to re-authenticate
    # For now, just redirect to logout/login flow
    logger.info("User requested Sync identity refresh")
    
    # Redirect to logout (which will clear Sync identity) then login
    return redirect(reverse('users:logout'))


# Decorator for views that require SyncServer authentication
def require_sync_auth(view_func):
    """
    Decorator to require SyncServer authentication for a view.
    
    Usage:
        @require_sync_auth
        def my_view(request):
            # This view will only be accessible if Sync identity exists
    
    Args:
        view_func: The view function to decorate
        
    Returns:
        Decorated view function
    """
    def wrapped_view(request, *args, **kwargs):
        if not has_sync_identity(request):
            logger.warning(
                "Sync authentication required but not found",
                extra={'path': request.path, 'user': request.user.username}
            )
            
            # Store current path for redirect after login
            request.session['sync_auth_redirect'] = request.get_full_path()
            
            # Redirect to error page or login
            return render(request, 'sync_auth/error.html', {
                'error': 'SyncServer authentication required.',
                'login_url': reverse('users:login')
            }, status=403)
        
        return view_func(request, *args, **kwargs)
    
    return wrapped_view


# Mixin for class-based views
class SyncAuthMixin:
    """
    Mixin for class-based views that require SyncServer authentication.
    
    Usage:
        class MyView(SyncAuthMixin, View):
            # This view will check Sync authentication in dispatch
    
    Methods:
        dispatch: Check Sync authentication before processing request
    """
    
    def dispatch(self, request, *args, **kwargs):
        if not has_sync_identity(request):
            logger.warning(
                "Sync authentication required but not found for class-based view",
                extra={'view': self.__class__.__name__, 'user': request.user.username}
            )
            
            # Store current path for redirect after login
            request.session['sync_auth_redirect'] = request.get_full_path()
            
            # Return error response
            return render(request, 'sync_auth/error.html', {
                'error': 'SyncServer authentication required.',
                'login_url': reverse('users:login')
            }, status=403)
        
        return super().dispatch(request, *args, **kwargs)