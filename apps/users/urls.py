from django.contrib.auth import views as auth_views
from django.urls import path

from . import sync_views

app_name = "users"

urlpatterns = [
    # Authentication views
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # SyncServer authentication views
    path("sync/site-switch/", sync_views.sync_site_switch, name="sync_site_switch"),
    path("sync/identity/", sync_views.sync_identity_info, name="sync_identity_info"),
    path("sync/refresh/", sync_views.sync_refresh_identity, name="sync_refresh_identity"),
]
