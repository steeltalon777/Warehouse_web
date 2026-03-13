from django.urls import path

from .views import AccessView, DevicesView, SitesView, UsersView

app_name = "admin_panel"

urlpatterns = [
    path("users/", UsersView.as_view(), name="users"),
    path("sites/", SitesView.as_view(), name="sites"),
    path("devices/", DevicesView.as_view(), name="devices"),
    path("access/", AccessView.as_view(), name="access"),
]
