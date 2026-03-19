from django.urls import path

from .views import (
    AccessView,
    DeviceCreateView,
    DevicesView,
    DeviceUpdateView,
    SiteCreateView,
    SitesView,
    SiteUpdateView,
    UserCreateView,
    UserToggleActiveView,
    UserUpdateView,
    UsersView,
    UserDeleteView
)
from .api_views import (
    APIUsersView,
    APIUserDetailView,
    APICreateUserView,
    APIUpdateUserView,
    APISitesView,
    APICreateSiteView,
    APIUpdateSiteView,
)

app_name = "admin_panel"

urlpatterns = [
    # Legacy views (using Django ORM + API mix)
    path("users/", UsersView.as_view(), name="users"),
    path("users/create/", UserCreateView.as_view(), name="user_create"),
    path("users/<str:username>/edit/", UserUpdateView.as_view(), name="user_edit"),
    path("users/<str:username>/toggle-active/", UserToggleActiveView.as_view(), name="user_toggle_active"),
    path("users/<str:username>/delete/", UserDeleteView.as_view(), name="user_delete"),

    path("sites/", SitesView.as_view(), name="sites"),
    path("sites/create/", SiteCreateView.as_view(), name="site_create"),
    path("sites/<str:id>/edit/", SiteUpdateView.as_view(), name="site_edit"),

    path("devices/", DevicesView.as_view(), name="devices"),
    path("devices/create/", DeviceCreateView.as_view(), name="device_create"),
    path("devices/<str:id>/edit/", DeviceUpdateView.as_view(), name="device_edit"),

    path("access/", AccessView.as_view(), name="access"),

    # New API-only views
    path("api/users/", APIUsersView.as_view(), name="api_users"),
    path("api/users/<str:user_id>/", APIUserDetailView.as_view(), name="api_user_detail"),
    path("api/users/create/", APICreateUserView.as_view(), name="api_user_create"),
    path("api/users/<str:user_id>/edit/", APIUpdateUserView.as_view(), name="api_user_edit"),

    path("api/sites/", APISitesView.as_view(), name="api_sites"),
    path("api/sites/create/", APICreateSiteView.as_view(), name="api_site_create"),
    path("api/sites/<str:site_id>/edit/", APIUpdateSiteView.as_view(), name="api_site_edit"),
]