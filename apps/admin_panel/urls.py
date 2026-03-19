from django.urls import path

from .views import (
    AccessView,
    DeviceCreateView,
    DevicesView,
    DeviceUpdateView,
)

app_name = "admin_panel"

urlpatterns = [
    path("devices/", DevicesView.as_view(), name="devices"),
    path("devices/create/", DeviceCreateView.as_view(), name="device_create"),
    path("devices/<str:id>/edit/", DeviceUpdateView.as_view(), name="device_edit"),

    path("access/", AccessView.as_view(), name="access"),
]
