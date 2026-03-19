from django.contrib.auth import views as auth_views
from django.urls import path

from . import sync_views
from .views import (
    # User views
    ListUsersView,
    UserDetailView,
    CreateUserView,
    UpdateUserView,
    # Site views
    ListSitesView,
    CreateSiteView,
    UpdateSiteView,
)

app_name = "users"

urlpatterns = [
    # Authentication views
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # SyncServer authentication views
    path("sync/site-switch/", sync_views.sync_site_switch, name="sync_site_switch"),
    path("sync/identity/", sync_views.sync_identity_info, name="sync_identity_info"),
    path("sync/refresh/", sync_views.sync_refresh_identity, name="sync_refresh_identity"),

    # User management URLs
    path("", ListUsersView.as_view(), name="list"),
    path("create/", CreateUserView.as_view(), name="create"),
    path("<str:user_id>/", UserDetailView.as_view(), name="detail"),
    path("<str:user_id>/update/", UpdateUserView.as_view(), name="update"),

    # Site management URLs
    path("sites/", ListSitesView.as_view(), name="sites_list"),
    path("sites/create/", CreateSiteView.as_view(), name="sites_create"),
    path("sites/<str:site_id>/update/", UpdateSiteView.as_view(), name="sites_update"),
]