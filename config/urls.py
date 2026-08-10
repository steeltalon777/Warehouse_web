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
from django.contrib.auth import views as auth_views
from django.urls import path, include, re_path
from django.views.generic import RedirectView

from apps.catalog.views import AngularStaticFilesView, CatalogSPAView, IssuedAssetsSPAView, OperationsSPAView, TemporaryItemsSPAView
from apps.common.views import HealthCheckView, SyncHealthCheckView
from apps.users.admin_audit_views import AdminAuditEventDetailView, AdminAuditEventListView
from apps.users.views import logout_view

urlpatterns = [
    # Angular built assets at root level (baseHref="/")
    re_path(r"^(?P<path>[\w-]+\.(?:js|css|map))$", AngularStaticFilesView.as_view(), name="angular_asset"),
    re_path(r"^(?P<path>favicon\.ico)$", AngularStaticFilesView.as_view(), name="angular_favicon"),

    path("admin/", admin.site.urls),

    # Catalog SSR fallback — must come BEFORE SPA catch-all so ssr/ paths are not swallowed
    path("catalog/ssr/", include("apps.catalog.urls")),
    # Catalog SPA — exact /catalog/ and catch-all render Angular SPA
    path("catalog/", CatalogSPAView.as_view(), name="catalog_spa"),
    path("catalog/<path:path>", CatalogSPAView.as_view(), name="catalog_spa_catchall"),
    path("nomenclature/", include("apps.catalog.nomenclature_urls")),
    path("client/", include("apps.client.urls")),
    # Operations SSR fallback — must come BEFORE SPA catch-all so ssr/ paths are not swallowed
    path("operations/ssr/", include("apps.operations.ssr_urls")),
    # Operations SPA — exact /operations/ and catch-all render Angular SPA
    path("operations/", OperationsSPAView.as_view(), name="operations_spa"),
    path("operations/<path:path>", OperationsSPAView.as_view(), name="operations_spa_catchall"),
    path("balances/", include("apps.balances.urls")),
    # Temporary Items SSR fallback — must come BEFORE SPA catch-all so ssr/ paths are not swallowed
    path("temporary-items/ssr/", include("apps.temporary_items.urls")),
    # Temporary Items SPA — exact /temporary-items/ and catch-all render Angular SPA
    path("temporary-items/", TemporaryItemsSPAView.as_view(), name="temporary_items_spa"),
    path("temporary-items/<path:path>", TemporaryItemsSPAView.as_view(), name="temporary_items_spa_catchall"),
    # Issued Assets SPA — exact /issued-assets/ and catch-all render Angular SPA
    path("issued-assets/", IssuedAssetsSPAView.as_view(), name="issued_assets_spa"),
    path("issued-assets/<path:path>", IssuedAssetsSPAView.as_view(), name="issued_assets_spa_catchall"),
    path("admin-panel/", include("apps.admin_panel.urls")),
    path("documents/", include("apps.documents.urls")),
    path("users/", include("apps.users.urls")),
    path(
        "admin/audit-events/",
        AdminAuditEventListView.as_view(),
        name="audit_events_list",
    ),
    path(
        "admin/audit-events/<uuid:event_id>/",
        AdminAuditEventDetailView.as_view(),
        name="audit_event_detail",
    ),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html"
        ),
        name="login",
    ),

    path(
        "logout/",
        logout_view,
        name="logout",
    ),

    path("users/password-reset/", auth_views.PasswordResetView.as_view(
        template_name="registration/password_reset_form.html",
        email_template_name="registration/password_reset_email.html",
    ), name="password_reset"),
    path("users/password-reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/password_reset_done.html",
    ), name="password_reset_done"),
    path("users/password-reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/password_reset_confirm.html",
    ), name="password_reset_confirm"),
    path("users/password-reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/password_reset_complete.html",
    ), name="password_reset_complete"),

    path("healthz/", HealthCheckView.as_view(), name="healthz"),
    path("bff/api/v1/", include("apps.bff_api.urls")),

    path("healthz/sync/", SyncHealthCheckView.as_view(), name="healthz_sync"),

    path("", RedirectView.as_view(url="/client/", permanent=False)),
]

# ---- PRODUCTION STATIC FILES FALLBACK ----
# Whitenoise is configured but not intercepting; serve /static/ directly
# via Django until Whitenoise is debugged.
import re
from django.conf import settings
from django.views.static import serve as static_serve
from django.urls import re_path
urlpatterns += [
    re_path(r"^static/(?P<path>.*)$", static_serve, {"document_root": settings.STATIC_ROOT}),
]
