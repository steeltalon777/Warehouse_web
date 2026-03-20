"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views

from apps.common.views import HealthCheckView, SyncHealthCheckView

urlpatterns = [

    path("admin/", admin.site.urls),

    path("catalog/", include("apps.catalog.urls")),
    path("nomenclature/", include("apps.catalog.nomenclature_urls")),
    path("client/", include("apps.client.urls")),
    path("operations/", include("apps.operations.urls")),
    path("balances/", include("apps.balances.urls")),
    path("admin-panel/", include("apps.admin_panel.urls")),
    path("documents/", include("apps.documents.urls")),
    path("users/", include("apps.users.urls")),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html"
        ),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path("healthz/", HealthCheckView.as_view(), name="healthz"),
    path("healthz/sync/", SyncHealthCheckView.as_view(), name="healthz_sync"),

    path("", RedirectView.as_view(url="/client/", permanent=False)),
]
