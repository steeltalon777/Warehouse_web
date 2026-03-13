from django.urls import path

from apps.catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.CatalogHomeView.as_view(), name="home"),
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/create/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categories/<uuid:pk>/edit/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categories/<uuid:pk>/deactivate/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("categories/tree/", views.CategoryTreeView.as_view(), name="category_tree"),
    path("units/", views.UnitListView.as_view(), name="unit_list"),
    path("units/create/", views.UnitCreateView.as_view(), name="unit_create"),
    path("units/<uuid:pk>/edit/", views.UnitUpdateView.as_view(), name="unit_update"),
    path("items/", views.ItemListView.as_view(), name="item_list"),
    path("items/create/", views.ItemCreateView.as_view(), name="item_create"),
    path("items/<uuid:pk>/edit/", views.ItemUpdateView.as_view(), name="item_update"),
    path("items/<uuid:pk>/deactivate/", views.ItemDeactivateView.as_view(), name="item_deactivate"),
]
