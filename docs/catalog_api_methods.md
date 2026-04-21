# Catalog API Client - Method List

## Overview

This document lists the main methods available in `apps/sync_client/catalog_api.py` and their corresponding SyncServer endpoints.

## Public Methods

### Legacy list methods

#### `list_items(filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/items`
- Returns: `list[dict]`
- Purpose: legacy flat item list access

#### `list_categories(filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/categories`
- Returns: `list[dict]`
- Purpose: legacy flat category list access

#### `get_categories_tree(*, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/categories/tree`
- Returns: `dict`
- Purpose: legacy tree payload access

#### `list_units(filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/units`
- Returns: `list[dict]`
- Purpose: units list access

### Browse / Read-Model methods

#### `browse_items(filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/read/items`
- Returns: `dict`
- Response shape: `{items, total_count, page, page_size}`
- Typical filters: `search`, `category_id`, `page`, `page_size`, `site_id`

#### `browse_categories(filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/read/categories`
- Returns: `dict`
- Response shape: `{categories, total_count, page, page_size}`
- Typical filters: `search`, `parent_id`, `page`, `page_size`, `include`, `items_preview_limit`, `site_id`

#### `browse_category_items(category_id, filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/read/categories/{category_id}/items`
- Returns: `dict`
- Response shape: `{items, total_count, page, page_size}`

#### `browse_category_children(category_id, filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/read/categories/{category_id}/children`
- Returns: `dict`
- Response shape: `{categories, total_count, page, page_size}`

#### `browse_category_parent_chain(category_id, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/read/categories/{category_id}/parent-chain`
- Returns: `dict`
- Response shape: `{category_id, parent_chain_summary}`

## Admin Methods

#### `list_admin_items(filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/admin/items`
- Returns: `dict`
- Response shape: `{items, total_count, page, page_size}`

#### `get_item(item_id, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/admin/items/{item_id}`

#### `create_item(payload, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `POST /catalog/admin/items`

#### `update_item(item_id, payload, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `PATCH /catalog/admin/items/{item_id}`

#### `delete_item(item_id, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `DELETE /catalog/admin/items/{item_id}`

#### `list_admin_categories(filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/admin/categories`
- Returns: `dict`
- Response shape: `{items, total_count, page, page_size}`

#### `get_category(category_id, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/admin/categories/{category_id}`

#### `create_category(payload, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `POST /catalog/admin/categories`

#### `update_category(category_id, payload, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `PATCH /catalog/admin/categories/{category_id}`

#### `delete_category(category_id, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `DELETE /catalog/admin/categories/{category_id}`

#### `list_admin_units(filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/admin/units`
- Returns: `dict`
- Response shape: `{items, total_count, page, page_size}`

#### `get_unit(unit_id, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /catalog/admin/units/{unit_id}`

#### `create_unit(payload, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `POST /catalog/admin/units`

#### `update_unit(unit_id, payload, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `PATCH /catalog/admin/units/{unit_id}`

#### `delete_unit(unit_id, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `DELETE /catalog/admin/units/{unit_id}`

## Recipient Reference Methods

These live in `apps/sync_client/recipients_api.py`.

#### `list_recipients(filters=None, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /recipients`
- Returns: `dict`
- Response shape: `{items, total_count, page, page_size}`

#### `create_recipient(payload, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `POST /recipients`

#### `merge_recipients(payload, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `POST /recipients/merge`

#### `get_recipient(recipient_id, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `GET /recipients/{recipient_id}`

#### `update_recipient(recipient_id, payload, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `PATCH /recipients/{recipient_id}`

#### `delete_recipient(recipient_id, *, acting_user_id=None, acting_site_id=None)`
- Endpoint: `DELETE /recipients/{recipient_id}`

## Architectural Note

- Read-only catalog pages in Django should prefer `/catalog/read/*`.
- Nomenclature management pages should use the admin CRUD endpoints.
- `site_id` in browse endpoints is access context, not a catalog data partition filter.
