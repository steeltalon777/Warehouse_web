"""
Django views for SyncServer users and sites management with unified error handling.

This module provides views for managing users and sites using SyncServer API
with unified error handling from apps.common.api_error_handler.

All views use API clients only, no ORM queries.
"""

import logging
from typing import Any

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.common.mixins import SyncAdminMixin
from apps.sync_client.exceptions import SyncServerAPIError

from apps.common.api_error_handler import (
    APIErrorHandler,
    handle_api_errors,
    safe_api_call,
    log_api_call,
)

logger = logging.getLogger(__name__)


# ============================================================================
# USER VIEWS
# ============================================================================

class ListUsersView(SyncAdminMixin, TemplateView):
    """
    View for listing all users from SyncServer.
    
    Endpoint: GET /admin/users
    Template: users/list.html
    """
    
    template_name = "users/list.html"
    
    @handle_api_errors(operation="Получение списка пользователей")
    def get_context_data(self, **kwargs) -> dict[str, Any]:
        """
        Get context data for template.
        
        Returns:
            dict: Context data with users list
        """
        context = super().get_context_data(**kwargs)
        users = []
        
        try:
            # Log API call
            log_api_call(
                method="GET",
                path="/admin/users",
                context={"view": "ListUsersView"}
            )
            
            users = self.users_api.list_users()
            logger.info(f"Fetched {len(users)} users from SyncServer")
            
        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                self.request, exc, "получении списка пользователей"
            )
        
        context["users"] = users
        return context


class UserDetailView(SyncAdminMixin, TemplateView):
    """
    View for displaying user details from SyncServer.
    
    Endpoint: GET /admin/users/{user_id}
    Template: users/detail.html
    """
    
    template_name = "users/detail.html"
    
    @handle_api_errors(operation="Получение деталей пользователя")
    def get_context_data(self, **kwargs) -> dict[str, Any]:
        """
        Get context data for template.
        
        Returns:
            dict: Context data with user details
        """
        context = super().get_context_data(**kwargs)
        user_id = kwargs.get("user_id")
        user = None
        
        if not user_id:
            messages.error(self.request, "Не указан ID пользователя")
            return context
        
        try:
            # Log API call
            log_api_call(
                method="GET",
                path=f"/admin/users/{user_id}",
                context={"user_id": user_id}
            )
            
            user = self.users_api.get_user(user_id)
            logger.info(f"Fetched user details for {user_id}")
            
        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                self.request, exc, "получении данных пользователя"
            )
        
        context["user"] = user
        context["user_id"] = user_id
        return context


class CreateUserView(SyncAdminMixin, View):
    """
    View for creating new user in SyncServer.
    
    GET: Display user creation form
    POST: Create user via API
    Template: users/form.html
    """
    
    template_name = "users/form.html"
    
    def get(self, request, *args, **kwargs):
        """
        Handle GET request - display user creation form.
        
        Returns:
            HttpResponse with user creation form
        """
        return render(request, self.template_name, {
            "form_title": "Создание пользователя",
            "action_url": reverse_lazy("users:create"),
            "user": None,
        })
    
    @handle_api_errors(operation="Создание пользователя")
    def post(self, request, *args, **kwargs):
        """
        Handle POST request - create user via API.
        
        Returns:
            HttpResponseRedirect to user detail or form with errors
        """
        # Extract form data
        user_data = {
            "username": request.POST.get("username", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "full_name": request.POST.get("full_name", "").strip(),
            "password": request.POST.get("password", ""),
            "role": request.POST.get("role", "storekeeper"),
            "is_root": request.POST.get("is_root") == "true",
        }
        
        # Basic validation
        if not user_data["username"]:
            messages.error(request, "Имя пользователя обязательно")
            return render(request, self.template_name, {
                "form_title": "Создание пользователя",
                "action_url": reverse_lazy("users:create"),
                "user": user_data,
                "errors": ["Имя пользователя обязательно"],
            })
        
        if not user_data["password"]:
            messages.error(request, "Пароль обязателен")
            return render(request, self.template_name, {
                "form_title": "Создание пользователя",
                "action_url": reverse_lazy("users:create"),
                "user": user_data,
                "errors": ["Пароль обязателен"],
            })
        
        try:
            # Log API call
            log_api_call(
                method="POST",
                path="/admin/users",
                context={"username": user_data["username"]}
            )
            
            # Create user via API
            created_user = self.users_api.create_user(user_data)
            user_id = created_user.get("id")
            
            messages.success(request, f"Пользователь {user_data['username']} успешно создан")
            logger.info(f"Created user {user_id} via SyncServer API")
            
            # Redirect to user detail page
            return redirect("users:detail", user_id=user_id)
            
        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "создании пользователя"
            )
            
            return render(request, self.template_name, {
                "form_title": "Создание пользователя",
                "action_url": reverse_lazy("users:create"),
                "user": user_data,
                "errors": [str(exc)],
            })


class UpdateUserView(SyncAdminMixin, View):
    """
    View for updating existing user in SyncServer.
    
    GET: Display user update form
    POST: Update user via API
    Template: users/form.html
    """
    
    template_name = "users/form.html"
    
    @handle_api_errors(operation="Получение данных пользователя для редактирования")
    def get(self, request, *args, **kwargs):
        """
        Handle GET request - display user update form.
        
        Returns:
            HttpResponse with user update form
        """
        user_id = kwargs.get("user_id")
        user = None
        
        if not user_id:
            messages.error(request, "Не указан ID пользователя")
            return redirect("users:list")
        
        try:
            # Log API call
            log_api_call(
                method="GET",
                path=f"/admin/users/{user_id}",
                context={"user_id": user_id, "action": "get_for_update"}
            )
            
            user = self.users_api.get_user(user_id)
            logger.info(f"Fetched user {user_id} for update")
            
        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "получении данных пользователя"
            )
            return redirect("users:list")
        
        return render(request, self.template_name, {
            "form_title": "Редактирование пользователя",
            "action_url": reverse_lazy("users:update", kwargs={"user_id": user_id}),
            "user": user,
        })
    
    @handle_api_errors(operation="Обновление пользователя")
    def post(self, request, *args, **kwargs):
        """
        Handle POST request - update user via API.
        
        Returns:
            HttpResponseRedirect to user detail or form with errors
        """
        user_id = kwargs.get("user_id")
        
        if not user_id:
            messages.error(request, "Не указан ID пользователя")
            return redirect("users:list")
        
        # Extract form data (password is optional for updates)
        user_data = {
            "username": request.POST.get("username", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "full_name": request.POST.get("full_name", "").strip(),
            "role": request.POST.get("role", "storekeeper"),
            "is_root": request.POST.get("is_root") == "true",
        }
        
        # Only include password if provided
        password = request.POST.get("password", "").strip()
        if password:
            user_data["password"] = password
        
        # Basic validation
        if not user_data["username"]:
            messages.error(request, "Имя пользователя обязательно")
            return render(request, self.template_name, {
                "form_title": "Редактирование пользователя",
                "action_url": reverse_lazy("users:update", kwargs={"user_id": user_id}),
                "user": user_data,
                "errors": ["Имя пользователя обязательно"],
            })
        
        try:
            # Log API call
            log_api_call(
                method="PATCH",
                path=f"/admin/users/{user_id}",
                context={"user_id": user_id, "username": user_data["username"]}
            )
            
            # Update user via API
            updated_user = self.users_api.update_user(user_id, user_data)
            
            messages.success(request, f"Пользователь {user_data['username']} успешно обновлён")
            logger.info(f"Updated user {user_id} via SyncServer API")
            
            # Redirect to user detail page
            return redirect("users:detail", user_id=user_id)
            
        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "обновлении пользователя"
            )
            
            return render(request, self.template_name, {
                "form_title": "Редактирование пользователя",
                "action_url": reverse_lazy("users:update", kwargs={"user_id": user_id}),
                "user": user_data,
                "errors": [str(exc)],
            })


# ============================================================================
# SITE VIEWS
# ============================================================================

class ListSitesView(SyncAdminMixin, TemplateView):
    """
    View for listing all sites from SyncServer.
    
    Endpoint: GET /admin/sites
    Template: sites/list.html
    """
    
    template_name = "sites/list.html"
    
    @handle_api_errors(operation="Получение списка складов")
    def get_context_data(self, **kwargs) -> dict[str, Any]:
        """
        Get context data for template.
        
        Returns:
            dict: Context data with sites list
        """
        context = super().get_context_data(**kwargs)
        sites = []
        
        try:
            # Log API call
            log_api_call(
                method="GET",
                path="/admin/sites",
                context={"view": "ListSitesView"}
            )
            
            sites = self.sites_api.list_sites()
            logger.info(f"Fetched {len(sites)} sites from SyncServer")
            
        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                self.request, exc, "получении списка складов"
            )
        
        context["sites"] = sites
        return context


class CreateSiteView(SyncAdminMixin, View):
    """
    View for creating new site in SyncServer.
    
    GET: Display site creation form
    POST: Create site via API
    Template: sites/form.html
    """
    
    template_name = "sites/form.html"
    
    def get(self, request, *args, **kwargs):
        """
        Handle GET request - display site creation form.
        
        Returns:
            HttpResponse with site creation form
        """
        return render(request, self.template_name, {
            "form_title": "Создание склада",
            "action_url": reverse_lazy("sites:create"),
            "site": None,
        })
    
    @handle_api_errors(operation="Создание склада")
    def post(self, request, *args, **kwargs):
        """
        Handle POST request - create site via API.
        
        Returns:
            HttpResponseRedirect to sites list or form with errors
        """
        # Extract form data
        site_data = {
            "name": request.POST.get("name", "").strip(),
            "code": request.POST.get("code", "").strip(),
            "description": request.POST.get("description", "").strip(),
            "address": request.POST.get("address", "").strip(),
            "timezone": request.POST.get("timezone", "Europe/Moscow"),
        }
        
        # Basic validation
        if not site_data["name"]:
            messages.error(request, "Название склада обязательно")
            return render(request, self.template_name, {
                "form_title": "Создание склада",
                "action_url": reverse_lazy("sites:create"),
                "site": site_data,
                "errors": ["Название склада обязательно"],
            })
        
        if not site_data["code"]:
            messages.error(request, "Код склада обязателен")
            return render(request, self.template_name, {
                "form_title": "Создание склада",
                "action_url": reverse_lazy("sites:create"),
                "site": site_data,
                "errors": ["Код склада обязателен"],
            })
        
        try:
            # Log API call
            log_api_call(
                method="POST",
                path="/admin/sites",
                context={"site_name": site_data["name"], "site_code": site_data["code"]}
            )
            
            # Create site via API
            created_site = self.sites_api.create_site(site_data)
            site_id = created_site.get("id")
            
            messages.success(request, f"Склад {site_data['name']} успешно создан")
            logger.info(f"Created site {site_id} via SyncServer API")
            
            # Redirect to sites list
            return redirect("sites:list")
            
        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "создании склада"
            )
            
            return render(request, self.template_name, {
                "form_title": "Создание склада",
                "action_url": reverse_lazy("sites:create"),
                "site": site_data,
                "errors": [str(exc)],
            })


class UpdateSiteView(SyncAdminMixin, View):
    """
    View for updating existing site in SyncServer.
    
    GET: Display site update form
    POST: Update site via API
    Template: sites/form.html
    """
    
    template_name = "sites/form.html"
    
    @handle_api_errors(operation="Получение данных склада для редактирования")
    def get(self, request, *args, **kwargs):
        """
        Handle GET request - display site update form.
        
        Returns:
            HttpResponse with site update form
        """
        site_id = kwargs.get("site_id")
        site = None
        
        if not site_id:
            messages.error(request, "Не указан ID склада")
            return redirect("sites:list")
        
        try:
            # Note: SitesAPI doesn't have get_site method, use list and filter
            # Log API call
            log_api_call(
                method="GET",
                path="/admin/sites",
                context={"site_id": site_id, "action": "get_for_update"}
            )
            
            sites = self.sites_api.list_sites()
            site = next((s for s in sites if s.get("id") == site_id), None)
            
            if not site:
                messages.error(request, f"Склад с ID {site_id} не найден")
                return redirect("sites:list")
                
            logger.info(f"Fetched site {site_id} for update")
            
        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "получении данных склада"
            )
            return redirect("sites:list")
        
        return render(request, self.template_name, {
            "form_title": "Редактирование склада",
            "action_url": reverse_lazy("sites:update", kwargs={"site_id": site_id}),
            "site": site,
        })
    
    @handle_api_errors(operation="Обновление склада")
    def post(self, request, *args, **kwargs):
        """
        Handle POST request - update site via API.
        
        Returns:
            HttpResponseRedirect to sites list or form with errors
        """
        site_id = kwargs.get("site_id")
        
        if not site_id:
            messages.error(request, "Не указан ID склада")
            return redirect("sites:list")
        
        # Extract form data
        site_data = {
            "name": request.POST.get("name", "").strip(),
            "code": request.POST.get("code", "").strip(),
            "description": request.POST.get("description", "").strip(),
            "address": request.POST.get("address", "").strip(),
            "timezone": request.POST.get("timezone", "Europe/Moscow"),
        }
        
        # Basic validation
        if not site_data["name"]:
            messages.error(request, "Название склада обязательно")
            return render(request, self.template_name, {
                "form_title": "Редактирование склада",
                "action_url": reverse_lazy("sites:update", kwargs={"site_id": site_id}),
                "site": site_data,
                "errors": ["Название склада обязательно"],
            })
        
        if not site_data["code"]:
            messages.error(request, "Код склада обязателен")
            return render(request, self.template_name, {
                "form_title": "Редактирование склада",
                "action_url": reverse_lazy("sites:update", kwargs={"site_id": site_id}),
                "site": site_data,
                "errors": ["Код склада обязателен"],
            })
        
        try:
            # Log API call
            log_api_call(
                method="PATCH",
                path=f"/admin/sites/{site_id}",
                context={"site_id": site_id, "site_name": site_data["name"]}
            )
            
            # Update site via API
            updated_site = self.sites_api.update_site(site_id, site_data)
            
            messages.success(request, f"Склад {site_data['name']} успешно обновлён")
            logger.info(f"Updated site {site_id} via SyncServer API")
            
            # Redirect to sites list
            return redirect("sites:list")
            
        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "обновлении склада"
            )
            
            return render(request, self.template_name, {
                "form_title": "Редактирование склада",
                "action_url": reverse_lazy("sites:update", kwargs={"site_id": site_id}),
                "site": site_data,
                "errors": [str(exc)],
            })