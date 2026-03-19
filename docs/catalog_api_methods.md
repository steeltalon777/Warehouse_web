# Catalog API Client - Method List

## Overview
This document lists all methods available in the `CatalogAPI` client module with their corresponding SyncServer endpoints.

## File Location
`apps/sync_client/catalog_api.py`

## Methods

### PUBLIC METHODS (Read-Only)

#### 1. `list_items(filters=None, *, acting_user_id=None, acting_site_id=None)`
**Description:** Get list of catalog items with optional filtering.

**Endpoint:** `GET /catalog/items`

**Parameters:**
- `filters` (Optional[dict]): Filter criteria (e.g., `category_id`, `search`, `is_active`)
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `list[dict]` - List of item dictionaries

**Example:**
```python
items = catalog_api.list_items(filters={
    "category_id": "cat-123",
    "search": "widget",
    "is_active": True
})
```

---

#### 2. `list_categories(filters=None, *, acting_user_id=None, acting_site_id=None)`
**Description:** Get list of catalog categories with optional filtering.

**Endpoint:** `GET /catalog/categories`

**Parameters:**
- `filters` (Optional[dict]): Filter criteria (e.g., `parent_id`, `is_active`)
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `list[dict]` - List of category dictionaries

**Example:**
```python
categories = catalog_api.list_categories(filters={
    "parent_id": "cat-123",
    "is_active": True
})
```

---

#### 3. `get_categories_tree(*, acting_user_id=None, acting_site_id=None)`
**Description:** Get hierarchical tree of catalog categories.

**Endpoint:** `GET /catalog/categories/tree`

**Parameters:**
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `dict` - Hierarchical tree structure of categories

**Example:**
```python
tree = catalog_api.get_categories_tree()
# Returns: {"id": "root", "name": "Root", "children": [...]}
```

---

#### 4. `list_units(filters=None, *, acting_user_id=None, acting_site_id=None)`
**Description:** Get list of measurement units with optional filtering.

**Endpoint:** `GET /catalog/units`

**Parameters:**
- `filters` (Optional[dict]): Filter criteria (e.g., `is_active`, `type`)
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `list[dict]` - List of unit dictionaries

**Example:**
```python
units = catalog_api.list_units(filters={
    "is_active": True,
    "type": "weight"
})
```

---

### ADMIN METHODS (Write)

#### 5. `create_item(payload, *, acting_user_id=None, acting_site_id=None)`
**Description:** Create new catalog item (admin only).

**Endpoint:** `POST /catalog/admin/items`

**Parameters:**
- `payload` (dict): Item creation data
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `dict` - Created item information

**Example:**
```python
new_item = catalog_api.create_item({
    "name": "Widget X100",
    "code": "WIDGET-X100",
    "category_id": "cat-123",
    "unit_id": "unit-456",
    "description": "High-quality widget",
    "is_active": True
})
```

---

#### 6. `update_item(item_id, payload, *, acting_user_id=None, acting_site_id=None)`
**Description:** Update existing catalog item (admin only).

**Endpoint:** `PATCH /catalog/admin/items/{item_id}`

**Parameters:**
- `item_id` (str): Item identifier to update
- `payload` (dict): Item update data (partial updates supported)
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `dict` - Updated item information

**Example:**
```python
updated_item = catalog_api.update_item("item-789", {
    "name": "Widget X100 Updated",
    "description": "Updated description",
    "is_active": False  # deactivate
})
```

---

#### 7. `create_category(payload, *, acting_user_id=None, acting_site_id=None)`
**Description:** Create new catalog category (admin only).

**Endpoint:** `POST /catalog/admin/categories`

**Parameters:**
- `payload` (dict): Category creation data
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `dict` - Created category information

**Example:**
```python
new_category = catalog_api.create_category({
    "name": "Electronics",
    "code": "ELEC",
    "parent_id": None,  # root category
    "sort_order": 10,
    "is_active": True
})
```

---

#### 8. `update_category(category_id, payload, *, acting_user_id=None, acting_site_id=None)`
**Description:** Update existing catalog category (admin only).

**Endpoint:** `PATCH /catalog/admin/categories/{category_id}`

**Parameters:**
- `category_id` (str): Category identifier to update
- `payload` (dict): Category update data (partial updates supported)
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `dict` - Updated category information

**Example:**
```python
updated_category = catalog_api.update_category("cat-123", {
    "name": "Electronics Updated",
    "sort_order": 15,
    "is_active": False  # deactivate
})
```

---

#### 9. `create_unit(payload, *, acting_user_id=None, acting_site_id=None)`
**Description:** Create new measurement unit (admin only).

**Endpoint:** `POST /catalog/admin/units`

**Parameters:**
- `payload` (dict): Unit creation data
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `dict` - Created unit information

**Example:**
```python
new_unit = catalog_api.create_unit({
    "name": "Kilogram",
    "code": "kg",
    "symbol": "kg",
    "is_active": True,
    "is_base": True,
    "conversion_factor": 1.0
})
```

---

#### 10. `update_unit(unit_id, payload, *, acting_user_id=None, acting_site_id=None)`
**Description:** Update existing measurement unit (admin only).

**Endpoint:** `PATCH /catalog/admin/units/{unit_id}`

**Parameters:**
- `unit_id` (str): Unit identifier to update
- `payload` (dict): Unit update data (partial updates supported)
- `acting_user_id` (Optional[str|int]): Acting user ID override
- `acting_site_id` (Optional[str|int]): Acting site ID override

**Returns:** `dict` - Updated unit information

**Example:**
```python
updated_unit = catalog_api.update_unit("unit-456", {
    "name": "Kilogram Updated",
    "symbol": "KG",
    "is_active": False  # deactivate
})
```

---

## Helper Methods

#### `_build_filter_params(filters)`
**Description:** Build query parameters from filters dictionary.

**Parameters:**
- `filters` (Optional[dict]): Dictionary of filter criteria

**Returns:** `dict` - Query parameters for HTTP request

**Internal use only.**

---

## Convenience Function

#### `get_catalog_api(client=None)`
**Description:** Get a CatalogAPI instance.

**Parameters:**
- `client` (Optional[SyncServerClient]): SyncServerClient instance

**Returns:** `CatalogAPI` instance

**Example:**
```python
from apps.sync_client.catalog_api import get_catalog_api

catalog_api = get_catalog_api()
```

---

## Endpoints Summary

| Method | HTTP Method | Endpoint | Description |
|--------|-------------|----------|-------------|
| `list_items` | GET | `/catalog/items` | List catalog items |
| `list_categories` | GET | `/catalog/categories` | List catalog categories |
| `get_categories_tree` | GET | `/catalog/categories/tree` | Get category hierarchy |
| `list_units` | GET | `/catalog/units` | List measurement units |
| `create_item` | POST | `/catalog/admin/items` | Create new item |
| `update_item` | PATCH | `/catalog/admin/items/{item_id}` | Update item |
| `create_category` | POST | `/catalog/admin/categories` | Create new category |
| `update_category` | PATCH | `/catalog/admin/categories/{category_id}` | Update category |
| `create_unit` | POST | `/catalog/admin/units` | Create new unit |
| `update_unit` | PATCH | `/catalog/admin/units/{unit_id}` | Update unit |

---

## Filter Parameters

### Common Filter Fields:
- `is_active` (bool): Filter by active status
- `search` (str): Text search across name/code fields

### Item-specific Filters:
- `category_id` (str): Filter by category
- `unit_id` (str): Filter by measurement unit

### Category-specific Filters:
- `parent_id` (str): Filter by parent category

### Unit-specific Filters:
- `type` (str): Filter by unit type (e.g., "weight", "volume")

---

## Error Handling

All methods raise `SyncAPIError` exceptions for API failures, with subclasses for specific error types:
- `SyncValidationError` (400, 422)
- `SyncAuthError` (401)
- `SyncForbiddenError` (403)
- `SyncNotFoundError` (404)
- `SyncConflictError` (409)
- `SyncServerInternalError` (≥500)

---

## Usage Example

```python
from apps.sync_client.client import SyncServerClient
from apps.sync_client.catalog_api import CatalogAPI

# Initialize client
client = SyncServerClient(user_id="admin", site_id="main")
catalog_api = CatalogAPI(client)

# Public operations
items = catalog_api.list_items(filters={"is_active": True})
categories = catalog_api.list_categories()
tree = catalog_api.get_categories_tree()
units = catalog_api.list_units(filters={"is_active": True})

# Admin operations (requires admin privileges)
new_item = catalog_api.create_item({
    "name": "New Product",
    "code": "PROD-001",
    "category_id": "cat-123",
    "unit_id": "unit-456"
})
```