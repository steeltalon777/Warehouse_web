from django.urls import path, include

from apps.bff_api import (
    admin_views,
    assets_views,
    auth_views,
    balances_views,
    catalog_views,
    documents_views,
    health_views,
    issue_objects_views,
    operations_views,
    reports_views,
    review_items_views,
    root_views,
    temp_items_views,
)

app_name = "bff_api"

auth_patterns = [
    path("auth/sync-user", auth_views.SyncUserView.as_view(), name="auth_sync_user"),
    path("auth/me", auth_views.MeView.as_view(), name="auth_me"),
    path("auth/sites", auth_views.SitesView.as_view(), name="auth_sites"),
    path("auth/context", auth_views.ContextView.as_view(), name="auth_context"),
]

admin_patterns = [
    path("admin/roles", admin_views.RolesView.as_view(), name="admin_roles"),
    path("admin/sites", admin_views.SitesListView.as_view(), name="admin_sites"),
    path("admin/sites/<str:site_id>", admin_views.SiteDetailView.as_view(), name="admin_site_detail"),
    path("admin/users", admin_views.UsersListView.as_view(), name="admin_users"),
    path("admin/users/<str:user_id>", admin_views.UserDetailView.as_view(), name="admin_user_detail"),
    path("admin/users/<str:user_id>/sync-state", admin_views.UserSyncStateView.as_view(), name="admin_user_sync_state"),
    path("admin/users/<str:user_id>/scopes", admin_views.UserScopesView.as_view(), name="admin_user_scopes"),
    path("admin/users/<str:user_id>/rotate-token", admin_views.UserRotateTokenView.as_view(), name="admin_user_rotate_token"),
    path("admin/access/scopes", admin_views.AccessScopesListView.as_view(), name="admin_access_scopes"),
    path("admin/access/scopes/<str:scope_id>", admin_views.AccessScopeDetailView.as_view(), name="admin_access_scope_detail"),
    path("admin/devices", admin_views.DevicesListView.as_view(), name="admin_devices"),
    path("admin/devices/<str:device_id>", admin_views.DeviceDetailView.as_view(), name="admin_device_detail"),
    path("admin/devices/<str:device_id>/rotate-token", admin_views.DeviceRotateTokenView.as_view(), name="admin_device_rotate_token"),
]

catalog_read_patterns = [
    path("catalog/items", catalog_views.ItemsView.as_view(), name="catalog_items"),
    path("catalog/categories", catalog_views.CategoriesView.as_view(), name="catalog_categories"),
    path("catalog/categories/tree", catalog_views.CategoriesTreeView.as_view(), name="catalog_categories_tree"),
    path("catalog/units", catalog_views.UnitsView.as_view(), name="catalog_units"),
    path("catalog/sites", catalog_views.CatalogSitesView.as_view(), name="catalog_sites"),
    path("catalog/read/items", catalog_views.BrowseItemsView.as_view(), name="catalog_read_items"),
    path("catalog/read/categories", catalog_views.BrowseCategoriesView.as_view(), name="catalog_read_categories"),
    path("catalog/read/categories/<str:category_id>/items", catalog_views.BrowseCategoryItemsView.as_view(), name="catalog_read_category_items"),
    path("catalog/read/categories/<str:category_id>/children", catalog_views.BrowseCategoryChildrenView.as_view(), name="catalog_read_category_children"),
    path("catalog/read/categories/<str:category_id>/parent-chain", catalog_views.BrowseCategoryParentChainView.as_view(), name="catalog_read_category_parent_chain"),
    # Cached search endpoints (cache-first, fallback, warm)
    path("catalog/search/items", catalog_views.CatalogCachedItemSearchView.as_view(), name="catalog_search_items"),
    path("catalog/search/categories", catalog_views.CatalogCachedCategorySearchView.as_view(), name="catalog_search_categories"),
]

catalog_admin_patterns = [
    path("catalog/admin/units", catalog_views.AdminUnitsListView.as_view(), name="catalog_admin_units"),
    path("catalog/admin/units/bulk", catalog_views.AdminUnitsBulkView.as_view(), name="catalog_admin_units_bulk"),
    path("catalog/admin/units/<str:unit_id>", catalog_views.AdminUnitDetailView.as_view(), name="catalog_admin_unit_detail"),
    path("catalog/admin/categories", catalog_views.AdminCategoriesListView.as_view(), name="catalog_admin_categories"),
    path("catalog/admin/categories/bulk", catalog_views.AdminCategoriesBulkView.as_view(), name="catalog_admin_categories_bulk"),
    path("catalog/admin/categories/<str:category_id>", catalog_views.AdminCategoryDetailView.as_view(), name="catalog_admin_category_detail"),
    path("catalog/admin/items", catalog_views.AdminItemsListView.as_view(), name="catalog_admin_items"),
    path("catalog/admin/items/<str:item_id>", catalog_views.AdminItemDetailView.as_view(), name="catalog_admin_item_detail"),
    path("catalog/admin/batch", catalog_views.AdminCatalogBatchView.as_view(), name="catalog_admin_batch"),
]

operations_patterns = [
    path("operations", operations_views.OperationsListView.as_view(), name="operations_list"),
    path("operations/<str:operation_id>", operations_views.OperationDetailView.as_view(), name="operation_detail"),
    path("operations/<str:operation_id>/effective-at", operations_views.OperationEffectiveAtView.as_view(), name="operation_effective_at"),
    path("operations/<str:operation_id>/submit", operations_views.OperationSubmitView.as_view(), name="operation_submit"),
    path("operations/<str:operation_id>/cancel", operations_views.OperationCancelView.as_view(), name="operation_cancel"),
    path("operations/<str:operation_id>/accept-lines", operations_views.OperationAcceptLinesView.as_view(), name="operation_accept_lines"),
]

balances_patterns = [
    path("balances", balances_views.BalancesView.as_view(), name="balances"),
    path("balances/by-site", balances_views.BalancesBySiteView.as_view(), name="balances_by_site"),
    path("balances/summary", balances_views.BalancesSummaryView.as_view(), name="balances_summary"),
]

temporary_items_patterns = [
    path("temporary-items", temp_items_views.TempItemsListView.as_view(), name="temp_items"),
    path("temporary-items/<str:temp_item_id>", temp_items_views.TempItemDetailView.as_view(), name="temp_item_detail"),
    path("temporary-items/<str:temp_item_id>/operations", temp_items_views.TempItemOperationsView.as_view(), name="temp_item_operations"),
    path("temporary-items/<str:temp_item_id>/approve-as-item", temp_items_views.TempItemApproveView.as_view(), name="temp_item_approve"),
    path("temporary-items/<str:temp_item_id>/merge", temp_items_views.TempItemMergeView.as_view(), name="temp_item_merge"),
]

review_items_patterns = [
    path("review-items", review_items_views.ReviewItemsListView.as_view(), name="review_items"),
    path("review-items/<int:item_id>", review_items_views.ReviewItemDetailView.as_view(), name="review_item_detail"),
    path("review-items/<int:item_id>/operations", review_items_views.ReviewItemOperationsView.as_view(), name="review_item_operations"),
    path("review-items/<int:item_id>/confirm", review_items_views.ReviewItemConfirmView.as_view(), name="review_item_confirm"),
    path("review-items/<int:item_id>/merge", review_items_views.ReviewItemMergeView.as_view(), name="review_item_merge"),
]

documents_patterns = [
    path("documents/generate", documents_views.DocumentGenerateView.as_view(), name="documents_generate"),
    path("documents", documents_views.DocumentsListView.as_view(), name="documents"),
    path("documents/<str:document_id>", documents_views.DocumentDetailView.as_view(), name="document_detail"),
    path("documents/<str:document_id>/render", documents_views.DocumentRenderView.as_view(), name="document_render"),
    path("documents/<str:document_id>/status", documents_views.DocumentStatusView.as_view(), name="document_status"),
    path("documents/operations/<str:operation_id>/documents", documents_views.OperationDocumentsView.as_view(), name="operation_documents"),
]

issue_objects_patterns = [
    path("issue-objects", issue_objects_views.IssueObjectsListView.as_view(), name="issue_objects_list"),
    path("issue-objects/merge", issue_objects_views.IssueObjectsMergeView.as_view(), name="issue_objects_merge"),
    path("issue-objects/<int:issue_object_id>", issue_objects_views.IssueObjectDetailView.as_view(), name="issue_object_detail"),
    path("issue-objects/<int:issue_object_id>/assets", issue_objects_views.ObjectAssetsListView.as_view(), name="issue_object_assets"),
]

assets_patterns = [
    path("pending-acceptance", assets_views.PendingAcceptanceView.as_view(), name="pending_acceptance"),
    path("lost-assets", assets_views.LostAssetsListView.as_view(), name="lost_assets"),
    path("lost-assets/<str:operation_line_id>", assets_views.LostAssetDetailView.as_view(), name="lost_asset_detail"),
    path("lost-assets/<str:operation_line_id>/resolve", assets_views.LostAssetResolveView.as_view(), name="lost_asset_resolve"),
    path("issued-assets", assets_views.IssuedAssetsView.as_view(), name="issued_assets"),
]

reports_patterns = [
    path("reports/item-movement", reports_views.ItemMovementView.as_view(), name="reports_item_movement"),
    path("reports/stock-summary", reports_views.StockSummaryView.as_view(), name="reports_stock_summary"),
]

health_patterns = [
    path("health", health_views.HealthView.as_view(), name="health"),
    path("ready", health_views.ReadyView.as_view(), name="ready"),
    path("health/detailed", health_views.HealthDetailedView.as_view(), name="health_detailed"),
    path("health/readiness", health_views.HealthReadinessView.as_view(), name="health_readiness"),
    path("health/liveness", health_views.HealthLivenessView.as_view(), name="health_liveness"),
]

urlpatterns = (
    auth_patterns
    + admin_patterns
    + catalog_read_patterns
    + catalog_admin_patterns
    + operations_patterns
    + balances_patterns
    + temporary_items_patterns
    + review_items_patterns
    + documents_patterns
    + issue_objects_patterns
    + assets_patterns
    + reports_patterns
    + health_patterns
    + [
        path("", root_views.RootView.as_view(), name="root"),
        path("db-check", root_views.DBCheckView.as_view(), name="db_check"),
    ]
)
