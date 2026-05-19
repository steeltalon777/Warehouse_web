from django.urls import path

from apps.catalog import api_views, views

app_name = "nomenclature"

# ---------------------------------------------------------------------------
# SSR fallback routes (preserved under /nomenclature/ssr/)
# URL names are kept identical to the old ones so all existing reverse() calls
# and template {% url %} tags continue to work without changes.
# ---------------------------------------------------------------------------
ssr_patterns = [
    path("ssr/", views.CatalogHomeView.as_view(), name="home"),
    path("ssr/tree/", views.NomenclatureTreeView.as_view(), name="tree"),
    path("ssr/cache/sync/", views.CatalogCacheSyncView.as_view(), name="cache_sync"),
    path("ssr/categories/", views.CategoryListView.as_view(), name="category_list"),
    path("ssr/categories/create/", views.CategoryCreateView.as_view(), name="category_create"),
    path("ssr/categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("ssr/categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("ssr/categories/merge/", views.CategoryMergeView.as_view(), name="category_merge"),
    path("ssr/categories/<int:pk>/deactivate/", views.CategoryDeleteView.as_view(), name="category_deactivate"),
    path("ssr/categories/tree/", views.CategoryTreeView.as_view(), name="category_tree"),
    path("ssr/units/", views.UnitListView.as_view(), name="unit_list"),
    path("ssr/units/create/", views.UnitCreateView.as_view(), name="unit_create"),
    path("ssr/units/<int:pk>/edit/", views.UnitUpdateView.as_view(), name="unit_update"),
    path("ssr/units/<int:pk>/delete/", views.UnitDeleteView.as_view(), name="unit_delete"),
    path("ssr/items/", views.ItemListView.as_view(), name="item_list"),
    path("ssr/items/create/", views.ItemCreateView.as_view(), name="item_create"),
    path("ssr/items/<int:pk>/edit/", views.ItemUpdateView.as_view(), name="item_update"),
    path("ssr/items/<int:pk>/delete/", views.ItemDeactivateView.as_view(), name="item_delete"),
    path("ssr/items/merge/", views.ItemMergeView.as_view(), name="item_merge"),
    path("ssr/items/<int:pk>/split/", views.ItemSplitView.as_view(), name="item_split"),
    path("ssr/items/<int:pk>/deactivate/", views.ItemDeactivateView.as_view(), name="item_deactivate"),
]

# ---------------------------------------------------------------------------
# BFF API endpoints — served under /nomenclature/api/
# These must come before the SPA catch-all.
# ---------------------------------------------------------------------------
api_patterns = [
    path("api/bootstrap/", api_views.BootstrapView.as_view(), name="api_bootstrap"),
    path("api/categories/", api_views.CategoryTreeView.as_view(), name="api_category_tree"),
    path("api/categories/<str:pk>/", api_views.CategoryDetailView.as_view(), name="api_category_detail"),
    path("api/items/", api_views.ItemsListView.as_view(), name="api_items_list"),
    path("api/items/<str:pk>/", api_views.ItemDetailView.as_view(), name="api_item_detail"),
    path("api/units/", api_views.UnitsListView.as_view(), name="api_units_list"),
    path("api/units/<str:pk>/", api_views.UnitDetailView.as_view(), name="api_unit_detail"),
]

# ---------------------------------------------------------------------------
# Angular SPA routes (must be last: catch-all)
# ---------------------------------------------------------------------------
spa_patterns = [
    path("", views.NomenclatureSPAView.as_view(), name="spa_home"),
    path("<path:path>", views.NomenclatureSPAView.as_view(), name="spa_catchall"),
]

urlpatterns = ssr_patterns + api_patterns + spa_patterns
