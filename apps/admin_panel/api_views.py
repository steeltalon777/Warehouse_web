"""
Django views for user and site management using SyncServer API only.

These views use the UsersAPI and SitesAPI clients to interact with SyncServer
without using Django ORM. All data operations go through SyncServer API.

Key principles:
1. No Django ORM queries - only API calls
2. Use UsersAPI and SitesAPI clients
3. Handle API errors with messages.error
4. Return context to templates
5. Follow existing URL patterns for compatibility
"""

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.common.mixins import SyncContextMixin
from apps.sync_client.exceptions import (
    SyncForbiddenError,
    SyncNotFoundError,
    SyncServerAPIError,
    SyncValidationError,
)
from apps.sync_client.users_api import UsersAPI, get_users_api
from apps.sync_client.sites_api import SitesAPI, get_sites_api

logger = logging.getLogger(__name__)


class RootOnlyMixin(UserPassesTestMixin):
    """Mixin to restrict access to root/admin users only."""
    
    def test_func(self) -> bool:
        return self.request.user.is_superuser


class APIUsersView(SyncContextMixin, RootOnlyMixin, TemplateView):
    """
    View for listing all users from SyncServer.
    
    Uses: UsersAPI.list_users()
    Template: admin_panel/users.html
    """
    template_name = "admin_panel/users.html"
    
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Get users list from SyncServer API."""
        context = super().get_context_data(**kwargs)
        users = []
        
        try:
            # Initialize UsersAPI with client from SyncContextMixin
            users_api = UsersAPI(self.client)
            users = users_api.list_users()
            logger.info(f"Retrieved {len(users)} users from SyncServer")
            
        except SyncServerAPIError as exc:
            logger.error(f"Failed to fetch users from SyncServer: {exc}")
            messages.error(self.request, f"Ошибка получения пользователей: {exc}")
        except Exception as exc:
            logger.exception("Unexpected error fetching users")
            messages.error(self.request, f"Неожиданная ошибка: {exc}")
        
        context['users'] = users
        return context


class APIUserDetailView(SyncContextMixin, RootOnlyMixin, View):
    """
    View for displaying user details from SyncServer.
    
    Uses: UsersAPI.get_user()
    Template: admin_panel/user_detail.html
    """
    template_name = "admin_panel/user_detail.html"
    
    def get(self, request: HttpRequest, user_id: str) -> HttpResponse:
        """Display user details."""
        try:
            users_api = UsersAPI(self.client)
            user = users_api.get_user(user_id)
            
            # Get user's sites access if needed
            # Note: This would require additional API calls or endpoint
            
            return render(request, self.template_name, {
                'user': user,
                'user_id': user_id,
            })
            
        except SyncNotFoundError:
            logger.warning(f"User not found: {user_id}")
            messages.error(request, f"Пользователь с ID {user_id} не найден")
            raise Http404("Пользователь не найден")
            
        except SyncServerAPIError as exc:
            logger.error(f"API error getting user {user_id}: {exc}")
            messages.error(request, f"Ошибка получения пользователя: {exc}")
            return redirect(reverse_lazy('admin_panel:users'))
            
        except Exception as exc:
            logger.exception(f"Unexpected error getting user {user_id}")
            messages.error(request, f"Неожиданная ошибка: {exc}")
            return redirect(reverse_lazy('admin_panel:users'))


class APICreateUserView(SyncContextMixin, RootOnlyMixin, View):
    """
    View for creating new user in SyncServer.
    
    Uses: UsersAPI.create_user()
    Template: admin_panel/user_form.html
    """
    template_name = "admin_panel/user_form.html"
    success_url = reverse_lazy("admin_panel:users")
    
    def get(self, request: HttpRequest) -> HttpResponse:
        """Display user creation form."""
        # Get available sites for the form
        sites = []
        try:
            sites_api = SitesAPI(self.client)
            sites = sites_api.list_sites()
        except SyncServerAPIError as exc:
            logger.warning(f"Failed to fetch sites for user creation: {exc}")
            messages.warning(request, f"Не удалось загрузить список складов: {exc}")
        
        return render(request, self.template_name, {
            'mode': 'create',
            'sites': sites,
            'form_data': {},
        })
    
    def post(self, request: HttpRequest) -> HttpResponse:
        """Create new user in SyncServer."""
        form_data = {
            'username': request.POST.get('username', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'full_name': request.POST.get('full_name', '').strip(),
            'password': request.POST.get('password', '').strip(),
            'is_active': request.POST.get('is_active') == 'on',
            'site_id': request.POST.get('site_id', '').strip(),
            'role': request.POST.get('role', 'storekeeper').strip(),
        }
        
        # Basic validation
        errors = {}
        if not form_data['username']:
            errors['username'] = 'Имя пользователя обязательно'
        if not form_data['password']:
            errors['password'] = 'Пароль обязателен'
        if not form_data['site_id']:
            errors['site_id'] = 'Склад обязателен'
        
        if errors:
            # Get sites for the form
            sites = []
            try:
                sites_api = SitesAPI(self.client)
                sites = sites_api.list_sites()
            except SyncServerAPIError:
                sites = []
            
            return render(request, self.template_name, {
                'mode': 'create',
                'sites': sites,
                'form_data': form_data,
                'errors': errors,
            })
        
        try:
            # Create user in SyncServer
            users_api = UsersAPI(self.client)
            
            # Prepare payload for user creation
            user_payload = {
                'username': form_data['username'],
                'email': form_data['email'],
                'full_name': form_data['full_name'],
                'password': form_data['password'],
                'is_active': form_data['is_active'],
            }
            
            # Remove empty fields
            user_payload = {k: v for k, v in user_payload.items() if v is not None and v != ''}
            
            # Create user
            created_user = users_api.create_user(user_payload)
            user_id = created_user.get('id')
            
            logger.info(f"Created user in SyncServer: {form_data['username']} (ID: {user_id})")
            
            # Note: Site access would be handled separately via AccessAPI
            # For now, we'll just show success message
            
            messages.success(request, f"Пользователь {form_data['username']} создан успешно")
            return redirect(self.success_url)
            
        except SyncValidationError as exc:
            logger.warning(f"Validation error creating user: {exc}")
            messages.error(request, f"Ошибка валидации: {exc}")
            
        except SyncServerAPIError as exc:
            logger.error(f"API error creating user: {exc}")
            messages.error(request, f"Ошибка создания пользователя: {exc}")
            
        except Exception as exc:
            logger.exception("Unexpected error creating user")
            messages.error(request, f"Неожиданная ошибка: {exc}")
        
        # If we get here, there was an error - redisplay form
        sites = []
        try:
            sites_api = SitesAPI(self.client)
            sites = sites_api.list_sites()
        except SyncServerAPIError:
            sites = []
        
        return render(request, self.template_name, {
            'mode': 'create',
            'sites': sites,
            'form_data': form_data,
            'errors': {'general': 'Не удалось создать пользователя'},
        })


class APIUpdateUserView(SyncContextMixin, RootOnlyMixin, View):
    """
    View for updating existing user in SyncServer.
    
    Uses: UsersAPI.update_user()
    Template: admin_panel/user_form.html
    """
    template_name = "admin_panel/user_form.html"
    success_url = reverse_lazy("admin_panel:users")
    
    def get(self, request: HttpRequest, user_id: str) -> HttpResponse:
        """Display user update form."""
        try:
            users_api = UsersAPI(self.client)
            user = users_api.get_user(user_id)
            
            # Get available sites for the form
            sites = []
            try:
                sites_api = SitesAPI(self.client)
                sites = sites_api.list_sites()
            except SyncServerAPIError as exc:
                logger.warning(f"Failed to fetch sites for user update: {exc}")
                messages.warning(request, f"Не удалось загрузить список складов: {exc}")
            
            form_data = {
                'username': user.get('username', ''),
                'email': user.get('email', ''),
                'full_name': user.get('full_name', ''),
                'is_active': user.get('is_active', True),
                # Note: site_id and role would come from access API
                'site_id': '',
                'role': 'storekeeper',
            }
            
            return render(request, self.template_name, {
                'mode': 'update',
                'user_id': user_id,
                'sites': sites,
                'form_data': form_data,
                'user': user,
            })
            
        except SyncNotFoundError:
            logger.warning(f"User not found for update: {user_id}")
            messages.error(request, f"Пользователь с ID {user_id} не найден")
            raise Http404("Пользователь не найден")
            
        except SyncServerAPIError as exc:
            logger.error(f"API error getting user for update: {exc}")
            messages.error(request, f"Ошибка получения пользователя: {exc}")
            return redirect(self.success_url)
            
        except Exception as exc:
            logger.exception(f"Unexpected error getting user {user_id}")
            messages.error(request, f"Неожиданная ошибка: {exc}")
            return redirect(self.success_url)
    
    def post(self, request: HttpRequest, user_id: str) -> HttpResponse:
        """Update user in SyncServer."""
        form_data = {
            'username': request.POST.get('username', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'full_name': request.POST.get('full_name', '').strip(),
            'password': request.POST.get('password', '').strip(),
            'is_active': request.POST.get('is_active') == 'on',
            'site_id': request.POST.get('site_id', '').strip(),
            'role': request.POST.get('role', 'storekeeper').strip(),
        }
        
        # Basic validation
        errors = {}
        if not form_data['username']:
            errors['username'] = 'Имя пользователя обязательно'
        
        if errors:
            # Get sites for the form
            sites = []
            try:
                sites_api = SitesAPI(self.client)
                sites = sites_api.list_sites()
            except SyncServerAPIError:
                sites = []
            
            return render(request, self.template_name, {
                'mode': 'update',
                'user_id': user_id,
                'sites': sites,
                'form_data': form_data,
                'errors': errors,
            })
        
        try:
            users_api = UsersAPI(self.client)
            
            # Prepare payload for user update
            user_payload = {
                'username': form_data['username'],
                'email': form_data['email'],
                'full_name': form_data['full_name'],
                'is_active': form_data['is_active'],
            }
            
            # Only include password if provided
            if form_data['password']:
                user_payload['password'] = form_data['password']
            
            # Remove empty fields
            user_payload = {k: v for k, v in user_payload.items() if v is not None and v != ''}
            
            # Update user
            updated_user = users_api.update_user(user_id, user_payload)
            
            logger.info(f"Updated user in SyncServer: {user_id}")
            
            # Note: Site access update would be handled separately via AccessAPI
            
            messages.success(request, f"Пользователь {form_data['username']} обновлен успешно")
            return redirect(self.success_url)
            
        except SyncNotFoundError:
            logger.warning(f"User not found during update: {user_id}")
            messages.error(request, f"Пользователь с ID {user_id} не найден")
            raise Http404("Пользователь не найден")
            
        except SyncValidationError as exc:
            logger.warning(f"Validation error updating user: {exc}")
            messages.error(request, f"Ошибка валидации: {exc}")
            
        except SyncServerAPIError as exc:
            logger.error(f"API error updating user: {exc}")
            messages.error(request, f"Ошибка обновления пользователя: {exc}")
            
        except Exception as exc:
            logger.exception("Unexpected error updating user")
            messages.error(request, f"Неожиданная ошибка: {exc}")
        
        # If we get here, there was an error - redisplay form
        sites = []
        try:
            sites_api = SitesAPI(self.client)
            sites = sites_api.list_sites()
        except SyncServerAPIError:
            sites = []
        
        return render(request, self.template_name, {
            'mode': 'update',
            'user_id': user_id,
            'sites': sites,
            'form_data': form_data,
            'errors': {'general': 'Не удалось обновить пользователя'},
        })


class APISitesView(SyncContextMixin, RootOnlyMixin, TemplateView):
    """
    View for listing all sites from SyncServer.
    
    Uses: SitesAPI.list_sites()
    Template: admin_panel/sites.html
    """
    template_name = "admin_panel/sites.html"
    
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Get sites list from SyncServer API."""
        context = super().get_context_data(**kwargs)
        sites = []
        
        try:
            sites_api = SitesAPI(self.client)
            sites = sites_api.list_sites()
            logger.info(f"Retrieved {len(sites)} sites from SyncServer")
            
        except SyncServerAPIError as exc:
            logger.error(f"Failed to fetch sites from SyncServer: {exc}")
            messages.error(self.request, f"Ошибка получения складов: {exc}")
        except Exception as exc:
            logger.exception("Unexpected error fetching sites")
            messages.error(self.request, f"Неожиданная ошибка: {exc}")
        
        context['sites'] = sites
        return context


class APICreateSiteView(SyncContextMixin, RootOnlyMixin, View):
    """
    View for creating new site in SyncServer.
    
    Uses: SitesAPI.create_site()
    Template: admin_panel/site_form.html
    """
    template_name = "admin_panel/site_form.html"
    success_url = reverse_lazy("admin_panel:sites")
    
    def get(self, request: HttpRequest) -> HttpResponse:
        """Display site creation form."""
        return render(request, self.template_name, {
            'mode': 'create',
            'form_data': {},
        })
    
    def post(self, request: HttpRequest) -> HttpResponse:
        """Create new site in SyncServer."""
        form_data = {
            'name': request.POST.get('name', '').strip(),
            'code': request.POST.get('code', '').strip(),
            'description': request.POST.get('description', '').strip(),
            'address': request.POST.get('address', '').strip(),
            'timezone': request.POST.get('timezone', 'UTC').strip(),
            'is_active': request.POST.get('is_active') == 'on',
        }
        
        # Basic validation
        errors = {}
        if not form_data['name']:
            errors['name'] = 'Название склада обязательно'
        if not form_data['code']:
            errors['code'] = 'Код склада обязателен'
        
        if errors:
            return render(request, self.template_name, {
                'mode': 'create',
                'form_data': form_data,
                'errors': errors,
            })
        
        try:
            sites_api = SitesAPI(self.client)
            
            # Prepare payload for site creation
            site_payload = {
                'name': form_data['name'],
                'code': form_data['code'],
                'description': form_data['description'],
                'address': form_data['address'],
                'timezone': form_data['timezone'],
                'is_active': form_data['is_active'],
            }
            
            # Remove empty fields
            site_payload = {k: v for k, v in site_payload.items() if v is not None and v != ''}
            
            # Create site
            created_site = sites_api.create_site(site_payload)
            site_id = created_site.get('id')
            
            logger.info(f"Created site in SyncServer: {form_data['name']} (ID: {site_id})")
            
            messages.success(request, f"Склад {form_data['name']} создан успешно")
            return redirect(self.success_url)
            
        except SyncValidationError as exc:
            logger.warning(f"Validation error creating site: {exc}")
            messages.error(request, f"Ошибка валидации: {exc}")
            
        except SyncServerAPIError as exc:
            logger.error(f"API error creating site: {exc}")
            messages.error(request, f"Ошибка создания склада: {exc}")
            
        except Exception as exc:
            logger.exception("Unexpected error creating site")
            messages.error(request, f"Неожиданная ошибка: {exc}")
        
        # If we get here, there was an error - redisplay form
        return render(request, self.template_name, {
            'mode': 'create',
            'form_data': form_data,
            'errors': {'general': 'Не удалось создать склад'},
        })


class APIUpdateSiteView(SyncContextMixin, RootOnlyMixin, View):
    """
    View for updating existing site in SyncServer.
    
    Uses: SitesAPI.update_site()
    Template: admin_panel/site_form.html
    """
    template_name = "admin_panel/site_form.html"
    success_url = reverse_lazy("admin_panel:sites")
    
    def get(self, request: HttpRequest, site_id: str) -> HttpResponse:
        """Display site update form."""
        try:
            sites_api = SitesAPI(self.client)
            
            # Get all sites and find the one we need
            sites = sites_api.list_sites()
            site = None
            for s in sites:
                if str(s.get('id')) == str(site_id):
                    site = s
                    break
            
            if not site:
                raise SyncNotFoundError(f"Site {site_id} not found")
            
            form_data = {
                'name': site.get('name', ''),
                'code': site.get('code', ''),
                'description': site.get('description', ''),
                'address': site.get('address', ''),
                'timezone': site.get('timezone', 'UTC'),
                'is_active': site.get('is_active', True),
            }
            
            return render(request, self.template_name, {
                'mode': 'update',
                'site_id': site_id,
                'form_data': form_data,
                'site': site,
            })
            
        except SyncNotFoundError:
            logger.warning(f"Site not found for update: {site_id}")
            messages.error(request, f"Склад с ID {site_id} не найден")
            raise Http404("Склад не найден")
            
        except SyncServerAPIError as exc:
            logger.error(f"API error getting site for update: {exc}")
            messages.error(request, f"Ошибка получения склада: {exc}")
            return redirect(self.success_url)
            
        except Exception as exc:
            logger.exception(f"Unexpected error getting site {site_id}")
            messages.error(request, f"Неожиданная ошибка: {exc}")
            return redirect(self.success_url)
    
    def post(self, request: HttpRequest, site_id: str) -> HttpResponse:
        """Update site in SyncServer."""
        form_data = {
            'name': request.POST.get('name', '').strip(),
            'code': request.POST.get('code', '').strip(),
            'description': request.POST.get('description', '').strip(),
            'address': request.POST.get('address', '').strip(),
            'timezone': request.POST.get('timezone', 'UTC').strip(),
            'is_active': request.POST.get('is_active') == 'on',
        }
        
        # Basic validation
        errors = {}
        if not form_data['name']:
            errors['name'] = 'Название склада обязательно'
        if not form_data['code']:
            errors['code'] = 'Код склада обязателен'
        
        if errors:
            return render(request, self.template_name, {
                'mode': 'update',
                'site_id': site_id,
                'form_data': form_data,
                'errors': errors,
            })
        
        try:
            sites_api = SitesAPI(self.client)
            
            # Prepare payload for site update
            site_payload = {
                'name': form_data['name'],
                'code': form_data['code'],
                'description': form_data['description'],
                'address': form_data['address'],
                'timezone': form_data['timezone'],
                'is_active': form_data['is_active'],
            }
            
            # Remove empty fields
            site_payload = {k: v for k, v in site_payload.items() if v is not None and v != ''}
            
            # Update site
            updated_site = sites_api.update_site(site_id, site_payload)
            
            logger.info(f"Updated site in SyncServer: {site_id}")
            
            messages.success(request, f"Склад {form_data['name']} обновлен успешно")
            return redirect(self.success_url)
            
        except SyncNotFoundError:
            logger.warning(f"Site not found during update: {site_id}")
            messages.error(request, f"Склад с ID {site_id} не найден")
            raise Http404("Склад не найден")
            
        except SyncValidationError as exc:
            logger.warning(f"Validation error updating site: {exc}")
            messages.error(request, f"Ошибка валидации: {exc}")
            
        except SyncServerAPIError as exc:
            logger.error(f"API error updating site: {exc}")
            messages.error(request, f"Ошибка обновления склада: {exc}")
            
        except Exception as exc:
            logger.exception("Unexpected error updating site")
            messages.error(request, f"Неожиданная ошибка: {exc}")
        
        # If we get here, there was an error - redisplay form
        return render(request, self.template_name, {
            'mode': 'update',
            'site_id': site_id,
            'form_data': form_data,
            'errors': {'general': 'Не удалось обновить склад'},
        })