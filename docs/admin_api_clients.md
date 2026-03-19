# Admin API Clients Documentation

## Overview

This document describes the new admin API clients created for SyncServer integration. These clients provide clean, separated interfaces for managing users, sites, and access permissions through the SyncServer API.

## Modules Created

### 1. `apps/sync_client/users_api.py`
High-level client for SyncServer admin users API.

**Methods:**
- `list_users()` - Get all users
- `get_user(user_id)` - Get specific user by ID
- `create_user(payload)` - Create new user
- `update_user(user_id, payload)` - Update existing user
- `delete_user(user_id)` - Delete user

**Endpoints used:**
- `GET /admin/users`
- `GET /admin/users/{user_id}`
- `POST /admin/users`
- `PATCH /admin/users/{user_id}`
- `DELETE /admin/users/{user_id}`

### 2. `apps/sync_client/sites_api.py`
High-level client for SyncServer admin sites API.

**Methods:**
- `list_sites()` - Get all sites
- `create_site(payload)` - Create new site
- `update_site(site_id, payload)` - Update existing site

**Endpoints used:**
- `GET /admin/sites`
- `POST /admin/sites`
- `PATCH /admin/sites/{site_id}`

### 3. `apps/sync_client/access_api.py`
High-level client for SyncServer admin access API.

**Methods:**
- `list_access()` - Get all user-site access records
- `create_access(payload)` - Create new access record
- `update_access(access_id, payload)` - Update existing access record

**Endpoints used:**
- `GET /admin/access/user-sites`
- `POST /admin/access/user-sites`
- `PATCH /admin/access/user-sites/{access_id}`

## Architecture Principles

### 1. Clean Separation
Each module handles exactly one domain:
- `users_api.py` - User management only
- `sites_api.py` - Site management only  
- `access_api.py` - Access control only

### 2. SyncServerClient Usage
All modules use the canonical `SyncServerClient` from `apps/sync_client/client.py` which:
- Handles service authentication
- Manages acting user/site headers
- Provides proper error handling
- Follows SyncServer API conventions

### 3. No Django ORM
These clients communicate directly with SyncServer API and do NOT use Django ORM for warehouse domain data. SyncServer remains the source of truth.

## Usage Examples

### Basic Usage

```python
from apps.sync_client.users_api import get_users_api
from apps.sync_client.sites_api import get_sites_api
from apps.sync_client.access_api import get_access_api

# Get API instances
users_api = get_users_api()
sites_api = get_sites_api()
access_api = get_access_api()

# List all users
users = users_api.list_users()
for user in users:
    print(user["username"], user["email"])

# List all sites
sites = sites_api.list_sites()
for site in sites:
    print(site["name"], site["code"])

# List all access records
access_records = access_api.list_access()
for record in access_records:
    print(f"User {record['user_id']} → Site {record['site_id']} ({record['role']})")
```

### Advanced Usage with Custom Context

```python
from apps.sync_client.client import SyncServerClient
from apps.sync_client.users_api import UsersAPI

# Create client with specific acting user/site
client = SyncServerClient(
    user_id="admin-user-123",
    site_id="main-site-456"
)

# Create API instance with custom client
users_api = UsersAPI(client)

# Use with custom acting context
users = users_api.list_users(
    acting_user_id="different-admin",
    acting_site_id="different-site"
)

# Create new user
new_user = users_api.create_user({
    "username": "john_doe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "password": "secure_password_123"
})

# Update user
updated_user = users_api.update_user("user-789", {
    "full_name": "John Doe Updated",
    "email": "john.updated@example.com"
})

# Delete user
users_api.delete_user("user-789")
```

### Error Handling

```python
from apps.sync_client.users_api import get_users_api
from apps.sync_client.exceptions import (
    SyncValidationError,
    SyncForbiddenError,
    SyncNotFoundError,
    SyncConflictError,
    SyncServerAPIError
)

users_api = get_users_api()

try:
    users = users_api.list_users()
except SyncValidationError as e:
    print(f"Validation error: {e}")
except SyncForbiddenError as e:
    print(f"Permission denied: {e}")
except SyncNotFoundError as e:
    print(f"Resource not found: {e}")
except SyncConflictError as e:
    print(f"Conflict: {e}")
except SyncServerAPIError as e:
    print(f"API error: {e}")
```

## Integration with Existing Code

### Backward Compatibility
The new modules are additive and don't break existing functionality. The existing `admin_api.py` remains functional.

### Migration Path
Existing code using `admin_api.py` can gradually migrate to the new separated APIs:

```python
# Old way (still works)
from apps.sync_client.admin_api import AdminAPI
admin_api = AdminAPI(client)
users = admin_api.users()

# New way (recommended)
from apps.sync_client.users_api import UsersAPI
users_api = UsersAPI(client)
users = users_api.list_users()
```

## Configuration Requirements

### Settings
The clients require these Django settings:

```python
# Required
SYNC_SERVER_URL = "http://sync-server:8000/api/v1"  # Must include /api/v1
SYNC_SERVER_SERVICE_TOKEN = "your-service-token-here"

# Optional with defaults
SYNC_SERVER_TIMEOUT = 10  # seconds
SYNC_DEFAULT_ACTING_USER_ID = "default-admin"
SYNC_DEFAULT_ACTING_SITE_ID = "default-site"
SYNC_WEB_DEVICE_ID = "00000000-0000-0000-0000-000000000001"
```

### Authentication
All requests use service authentication with:
- `Authorization: Bearer {service_token}`
- `X-Acting-User-Id: {user_id}`
- `X-Acting-Site-Id: {site_id}`
- Compatibility headers: `X-User-Id`, `X-Site-Id`, `X-Device-Id`

## Testing

Run the example script to verify installation:

```bash
cd apps/sync_client
python admin_api_example.py
```

## Files Created

1. `apps/sync_client/users_api.py` - Users API client
2. `apps/sync_client/sites_api.py` - Sites API client  
3. `apps/sync_client/access_api.py` - Access API client
4. `apps/sync_client/admin_api_example.py` - Usage examples
5. `docs/admin_api_clients.md` - This documentation

## Endpoints Summary

| Module | Method | Endpoint | Description |
|--------|--------|----------|-------------|
| UsersAPI | GET | `/admin/users` | List all users |
| UsersAPI | GET | `/admin/users/{id}` | Get specific user |
| UsersAPI | POST | `/admin/users` | Create user |
| UsersAPI | PATCH | `/admin/users/{id}` | Update user |
| UsersAPI | DELETE | `/admin/users/{id}` | Delete user |
| SitesAPI | GET | `/admin/sites` | List all sites |
| SitesAPI | POST | `/admin/sites` | Create site |
| SitesAPI | PATCH | `/admin/sites/{id}` | Update site |
| AccessAPI | GET | `/admin/access/user-sites` | List all access records |
| AccessAPI | POST | `/admin/access/user-sites` | Create access record |
| AccessAPI | PATCH | `/admin/access/user-sites/{id}` | Update access record |

## Notes

1. All operations require admin privileges in SyncServer
2. The `access_id` in AccessAPI refers to the user-site relationship ID
3. Update operations support partial updates (PATCH semantics)
4. Error handling is consistent across all modules
5. Logging is integrated for debugging and monitoring