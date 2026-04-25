from django.urls import path

from .views import (
    AcceptanceDetailView,
    AcceptanceSubmitView,
    CancelOperationView,
    LostAssetDetailView,
    LostAssetResolveView,
    LostAssetsListView,
    OperationCreateView,
    OperationDetailView,
    OperationItemCreateView,
    OperationItemSearchView,
    OperationsListView,
    PendingAcceptanceListView,
    SubmitOperationView,
)

app_name = "operations"

urlpatterns = [
    path("", OperationsListView.as_view(), name="list"),
    path("create/", OperationCreateView.as_view(), name="create"),
    path("item-search/", OperationItemSearchView.as_view(), name="item_search"),
    path("item-create/", OperationItemCreateView.as_view(), name="item_create"),
    path("pending-acceptance/", PendingAcceptanceListView.as_view(), name="pending_acceptance"),
    path("lost-assets/", LostAssetsListView.as_view(), name="lost_assets"),
    path("lost-assets/<str:operation_line_id>/", LostAssetDetailView.as_view(), name="lost_asset_detail"),
    path("lost-assets/<str:operation_line_id>/resolve/", LostAssetResolveView.as_view(), name="lost_asset_resolve"),
    path("<str:operation_id>/", OperationDetailView.as_view(), name="detail"),
    path("<str:operation_id>/submit/", SubmitOperationView.as_view(), name="submit"),
    path("<str:operation_id>/cancel/", CancelOperationView.as_view(), name="cancel"),
    path("<str:operation_id>/acceptance/", AcceptanceDetailView.as_view(), name="acceptance_detail"),
    path("<str:operation_id>/acceptance/submit/", AcceptanceSubmitView.as_view(), name="acceptance_submit"),
]
