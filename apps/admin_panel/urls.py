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
    UserUpdateView,
    UserToggleActiveView,
    UsersView,
)

app_name = "admin_panel"

urlpatterns = [
    path("users/", UsersView.as_view(), name="users"),
    path("users/create/", UserCreateView.as_view(), name="user_create"),
    path("users/<int:user_id>/edit/", UserUpdateView.as_view(), name="user_edit"),
    path("users/<int:user_id>/toggle-active/", UserToggleActiveView.as_view(), name="user_toggle_active"),

    path("sites/", SitesView.as_view(), name="sites"),
    path("sites/create/", SiteCreateView.as_view(), name="site_create"),
    path("sites/<str:id>/edit/", SiteUpdateView.as_view(), name="site_edit"),

    path("devices/", DevicesView.as_view(), name="devices"),
    path("devices/create/", DeviceCreateView.as_view(), name="device_create"),
    path("devices/<str:id>/edit/", DeviceUpdateView.as_view(), name="device_edit"),

    path("access/", AccessView.as_view(), name="access"),
]