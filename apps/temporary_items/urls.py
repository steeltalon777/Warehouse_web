from django.urls import path

from .views import (
    TemporaryItemApproveView,
    TemporaryItemBulkDeleteView,
    TemporaryItemCatalogSearchView,
    TemporaryItemDeleteView,
    TemporaryItemDetailView,
    TemporaryItemListView,
    TemporaryItemMergeView,
)

app_name = "temporary_items"

urlpatterns = [
    path("", TemporaryItemListView.as_view(), name="list"),
    path("bulk-delete/", TemporaryItemBulkDeleteView.as_view(), name="bulk_delete"),
    path("item-search/", TemporaryItemCatalogSearchView.as_view(), name="item_search"),
    path("<str:item_id>/", TemporaryItemDetailView.as_view(), name="detail"),
    path("<str:item_id>/approve/", TemporaryItemApproveView.as_view(), name="approve"),
    path("<str:item_id>/merge/", TemporaryItemMergeView.as_view(), name="merge"),
    path("<str:item_id>/delete/", TemporaryItemDeleteView.as_view(), name="delete"),
]
