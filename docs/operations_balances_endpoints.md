# Operations and Balances API Clients - Endpoint Mapping

## Overview
This document provides the endpoint mapping for the OperationsAPI and BalancesAPI clients with their corresponding SyncServer endpoints.

## Files Created/Updated

### 1. `apps/sync_client/operations_api.py`
**Description:** API client for inventory operations management (receipts, issues, transfers).

**Backup:** `apps/sync_client/operations_api_old.py` (original version preserved)

### 2. `apps/sync_client/balances_api.py`
**Description:** API client for inventory balances queries.

**Backup:** `apps/sync_client/balances_api_old.py` (original version preserved)

## OperationsAPI - Endpoint Mapping

### Method: `list_operations(filters=None, *, acting_user_id=None, acting_site_id=None)`
**HTTP Method:** GET  
**Endpoint:** `/operations`  
**Description:** Get list of operations with optional filtering.

**Filter Parameters:**
- `status` (str): Operation status (draft, submitted, completed, cancelled)
- `type` (str): Operation type (receipt, issue, transfer, adjustment)
- `item_id` (str): Filter by item
- `site_id` (str): Filter by site
- `created_by` (str): Filter by creator
- `created_after` (datetime): Filter by creation date
- `created_before` (datetime): Filter by creation date
- `search` (str): Text search across operation fields

---

### Method: `get_operation(operation_id, *, acting_user_id=None, acting_site_id=None)`
**HTTP Method:** GET  
**Endpoint:** `/operations/{operation_id}`  
**Description:** Get specific operation by ID.

**Path Parameter:**
- `operation_id` (str): Operation identifier

---

### Method: `create_operation(payload, *, acting_user_id=None, acting_site_id=None)`
**HTTP Method:** POST  
**Endpoint:** `/operations`  
**Description:** Create new inventory operation.

**Request Body (payload):**
```json
{
  "type": "receipt",
  "item_id": "item-123",
  "quantity": 10.5,
  "unit_id": "unit-456",
  "site_id": "site-789",
  "target_site_id": "site-999",
  "notes": "Operation description",
  "status": "draft"
}
```

---

### Method: `update_operation(operation_id, payload, *, acting_user_id=None, acting_site_id=None)`
**HTTP Method:** PATCH  
**Endpoint:** `/operations/{operation_id}`  
**Description:** Update existing operation.

**Path Parameter:**
- `operation_id` (str): Operation identifier to update

**Request Body (payload):**
Partial update supported. Can include any operation fields.

---

### Method: `submit_operation(operation_id, *, acting_user_id=None, acting_site_id=None)`
**HTTP Method:** POST  
**Endpoint:** `/operations/{operation_id}/submit`  
**Description:** Submit operation for processing (draft → submitted).

**Path Parameter:**
- `operation_id` (str): Operation identifier to submit

---

### Method: `cancel_operation(operation_id, *, acting_user_id=None, acting_site_id=None)`
**HTTP Method:** POST  
**Endpoint:** `/operations/{operation_id}/cancel`  
**Description:** Cancel operation (draft/submitted → cancelled).

**Path Parameter:**
- `operation_id` (str): Operation identifier to cancel

---

## BalancesAPI - Endpoint Mapping

### Method: `list_balances(filters=None, *, acting_user_id=None, acting_site_id=None)`
**HTTP Method:** GET  
**Endpoint:** `/balances`  
**Description:** Get list of inventory balances with optional filtering.

**Filter Parameters:**
- `item_id` (str): Filter by item
- `site_id` (str): Filter by site
- `min_quantity` (float): Minimum quantity filter
- `max_quantity` (float): Maximum quantity filter
- `item_category_id` (str): Filter by item category
- `updated_after` (datetime): Filter by update date
- `updated_before` (datetime): Filter by update date
- `search` (str): Text search across item/site fields

---

### Method: `get_balances_summary(filters=None, *, acting_user_id=None, acting_site_id=None)`
**HTTP Method:** GET  
**Endpoint:** `/balances/summary`  
**Description:** Get summary statistics for inventory balances.

**Filter Parameters:**
- `site_id` (str): Filter summary by site
- `item_category_id` (str): Filter by item category

**Response Example:**
```json
{
  "total_items": 150,
  "total_quantity": 1250.5,
  "total_value": 25000.75,
  "low_stock_items": 12,
  "out_of_stock_items": 3,
  "by_site": {
    "site-456": {
      "item_count": 75,
      "total_quantity": 625.25
    }
  }
}
```

---

### Method: `get_balances_by_item(item_id, *, acting_user_id=None, acting_site_id=None)`
**HTTP Method:** GET  
**Endpoint:** `/balances/items/{item_id}`  
**Description:** Get balances for specific item across all sites.

**Path Parameter:**
- `item_id` (str): Item identifier

**Response Example:**
```json
[
  {
    "site_id": "site-456",
    "site_name": "Main Warehouse",
    "quantity": 25.5,
    "unit_id": "unit-789",
    "unit_name": "kg",
    "updated_at": "2024-01-15T10:30:00Z"
  }
]
```

---

## Common Features

### 1. Filter Support
Both APIs support comprehensive filtering through query parameters:
- All `list_*` methods accept `filters` parameter
- Filters are converted to query parameters
- Supports equality, range, and text search filters

### 2. Acting Context
All methods support optional `acting_user_id` and `acting_site_id` parameters:
- Override default acting context from SyncServerClient
- Useful for impersonation or service accounts
- Maintains service authentication headers

### 3. Error Handling
Consistent error handling across all methods:
- Raises `SyncAPIError` for API failures
- Subclasses for specific error types (validation, auth, not found, etc.)
- Detailed error messages and status codes

### 4. Response Format Handling
Robust handling of different response formats:
- Extracts data from `operations`/`balances` keys if present
- Falls back to direct list response
- Logs warnings for unexpected formats

---

## Usage Examples

### OperationsAPI Example
```python
from apps.sync_client.client import SyncServerClient
from apps.sync_client.operations_api import OperationsAPI

client = SyncServerClient(user_id="storekeeper", site_id="warehouse-1")
operations_api = OperationsAPI(client)

# Create receipt operation
receipt = operations_api.create_operation({
    "type": "receipt",
    "item_id": "widget-123",
    "quantity": 100,
    "site_id": "warehouse-1",
    "notes": "Monthly supplier delivery"
})

# Submit for processing
operations_api.submit_operation(receipt["id"])

# List draft operations
drafts = operations_api.list_operations(filters={"status": "draft"})
```

### BalancesAPI Example
```python
from apps.sync_client.client import SyncServerClient
from apps.sync_client.balances_api import BalancesAPI

client = SyncServerClient(user_id="manager", site_id="warehouse-1")
balances_api = BalancesAPI(client)

# Get low stock items
low_stock = balances_api.list_balances(filters={"max_quantity": 10})

# Get summary for warehouse
summary = balances_api.get_balances_summary(filters={"site_id": "warehouse-1"})

# Check item availability across all sites
item_balances = balances_api.get_balances_by_item("widget-123")
total_quantity = sum(b["quantity"] for b in item_balances)
```

---

## Migration Notes

### From Old Version
1. **OperationsAPI:**
   - `list()` → `list_operations()` (added filter support)
   - `get()` → `get_operation()` (renamed for clarity)
   - `create()` → `create_operation()` (renamed for clarity)
   - `update()` → `update_operation()` (renamed for clarity)
   - `submit()` → `submit_operation()` (renamed for clarity)
   - `cancel()` → `cancel_operation()` (renamed for clarity)

2. **BalancesAPI:**
   - `list()` → `list_balances()` (added filter support)
   - `summary()` → `get_balances_summary()` (renamed, added filter support)
   - `by_site()` - deprecated in favor of `list_balances(filters={"site_id": ...})`
   - Added `get_balances_by_item()` method

### Backward Compatibility
- Old backup files preserved as `*_old.py`
- Existing code using old method names will need updates
- New methods provide enhanced functionality and better naming

---

## Testing Notes

**NOT VERIFIED** - Real testing requires:
1. SyncServer with operations and balances endpoints
2. Service authentication token
3. Valid acting user and site context
4. Test data for operations and balances

Recommended test scenarios:
1. Create → Submit → Complete operation lifecycle
2. Filter operations by status, type, item, site
3. Query balances with quantity range filters
4. Get item balances across multiple sites
5. Test error handling for invalid operations