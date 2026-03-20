from django.urls import path

from apps.catalog import browse_views

app_name = "catalog"

urlpatterns = [
    path("", browse_views.CatalogHomeView.as_view(), name="home"),
    path("items/", browse_views.BrowseItemListView.as_view(), name="item_list"),
    path("categories/", browse_views.BrowseCategoryListView.as_view(), name="category_list"),
]
