# SyncServer Authentication Integration with Django Session

## Overview

This document describes the integration of SyncServer authentication with Django's session system. After successful Django login, the system automatically authenticates with SyncServer and stores the SyncServer identity in the Django session.

## Architecture

### Two-Layer Authentication
1. **Django Authentication** - Technical admin/staff layer (username/password)
2. **SyncServer Authentication** - Domain user identity (tokens, roles, sites)

### Flow
1. User logs in via Django login form
2. Django authenticates user (checks username/password in Django database)
3. Signal triggers SyncServer authentication
4. SyncServer returns identity (token, user ID, role, sites)
5. Identity stored in Django session
6. Subsequent requests use SyncServer token for API calls

## Files Created/Updated

### New Files:
1. **`apps/sync_client/auth_integration.py`** - Core integration logic
   - `SyncIdentity` dataclass
   - `sync_auth_login()` / `sync_auth_logout()` functions
   - `get_sync_identity()` helper
   - Context processor for templates

2. **`apps/users/sync_signals.py`** - Django signals
   - `on_user_logged_in` - Triggers SyncServer auth after Django login
   - `on_user_logged_out` - Clears SyncServer identity
   - `SyncAuthMiddleware` - Middleware for validation
   - `require_sync_auth` decorator

3. **`apps/users/sync_views.py`** - Management views
   - Site switching view
   - Identity information view
   - Authentication decorators and mixins

4. **Templates** (`templates/sync_auth/`):
   - `site_switch.html` - Site selection interface
   - `identity_info.html` - Identity display
   - `error.html` - Authentication error page

### Updated Files:
1. **`apps/users/apps.py`** - Registered sync signals
2. **`apps/users/urls.py`** - Added SyncServer auth URLs
3. **`apps/sync_client/simple_client.py`** - Updated to use new session structure
4. **`apps/sync_client/__init__.py`** - Added auth_integration exports

## Session Storage

### Session Keys Stored:
- `sync_user_token` - SyncServer user authentication token
- `sync_user_id` - SyncServer user identifier
- `sync_role` - User role (storekeeper, chief, root)
- `sync_is_root` - Boolean indicating root/admin privileges
- `sync_available_sites` - List of sites user has access to
- `sync_default_site_id` - Default site ID for operations

### Legacy Compatibility:
- `user_token` - Also stored for backward compatibility with existing SyncClient

## Helper Functions

### `get_sync_identity(request)`
```python
from apps.sync_client.auth_integration import get_sync_identity

identity = get_sync_identity(request)
if identity:
    print(f"User ID: {identity.user_id}")
    print(f"Role: {identity.role}")
    print(f"Site ID: {identity.site_id}")
    print(f"Has root: {identity.is_root}")
    print(f"Available sites: {len(identity.available_sites)}")
```

### `has_sync_identity(request)`
Check if SyncServer identity exists in session.

### `update_sync_site(request, site_id)`
Switch to a different site (must be in available_sites).

## Usage in Views

### Function-Based Views:
```python
from apps.sync_client.auth_integration import require_sync_auth

@require_sync_auth
def protected_view(request):
    identity = request.sync_identity
    # View logic here
```

### Class-Based Views:
```python
from apps.sync_client.auth_integration import SyncAuthMixin
from django.views import View

class ProtectedView(SyncAuthMixin, View):
    def get(self, request):
        identity = request.sync_identity
        # View logic here
```

### Template Context:
```django
{% if sync_identity %}
    <p>User: {{ sync_identity.user_id }}</p>
    <p>Role: {{ sync_identity.role }}</p>
    <p>Site: {{ sync_identity.site_id }}</p>
    
    {% if sync_identity.is_root %}
        <span class="badge badge-danger">Root</span>
    {% endif %}
{% endif %}
```

## Middleware

### `SyncAuthMiddleware`
Add to `MIDDLEWARE` in settings to automatically:
- Add `sync_identity` to request object
- Add `has_sync_identity` boolean to request
- Validate authentication for protected paths

```python
# config/settings/base.py
MIDDLEWARE = [
    # ...
    'apps.users.sync_signals.SyncAuthMiddleware',
    # ...
]
```

## Context Processor

### `sync_identity_context`
Add to `TEMPLATES.context_processors` to make Sync identity available in all templates:

```python
# config/settings/base.py
TEMPLATES = [
    {
        'OPTIONS': {
            'context_processors': [
                # ...
                'apps.sync_client.auth_integration.sync_identity_context',
                # ...
            ],
        },
    },
]
```

## URLs

### Available Routes:
- `/users/sync/site-switch/` - Switch between available sites
- `/users/sync/identity/` - View identity information
- `/users/sync/refresh/` - Refresh identity (redirects to logout/login)

## Error Handling

### Authentication Errors:
- Missing Sync identity triggers 403 error page
- Invalid site access attempts are blocked
- Session corruption is detected and cleared

### Graceful Degradation:
- Django login succeeds even if SyncServer is unavailable
- Views can check `has_sync_identity` and provide fallback behavior
- Legacy code continues to work with `user_token` session key

## Security Considerations

### Token Storage:
- SyncServer tokens stored in Django session (server-side)
- Tokens are not exposed to client JavaScript
- Session cookies are HttpOnly and Secure (when HTTPS)

### Validation:
- Each request validates session existence
- Site access is checked before allowing operations
- Root privileges are explicitly checked

### Cleanup:
- Tokens cleared on logout
- Session expiry follows Django settings
- No persistent token storage outside session

## Migration Notes

### From Old System:
1. Existing code using `request.session.get('user_token')` continues to work
2. New code should use `get_sync_identity(request)` for structured access
3. SyncClient automatically uses new `sync_user_token` if available

### Testing:
1. Test Django login with valid SyncServer credentials
2. Test site switching functionality
3. Verify identity persists across requests
4. Test logout clears all session data

## Configuration

### Required Settings:
```python
# Already in config/settings/base.py
SYNC_SERVER_URL = "http://syncserver:8000/api/v1"
SYNC_SERVER_SERVICE_TOKEN = "your-service-token"
```

### Optional Settings:
```python
# Default acting context for service accounts
SYNC_DEFAULT_ACTING_USER_ID = "service-account"
SYNC_DEFAULT_ACTING_SITE_ID = "default-site"
```

## Troubleshooting

### Common Issues:

1. **No Sync identity after login**
   - Check SyncServer connectivity
   - Verify service token is configured
   - Check authentication logs

2. **Site switching fails**
   - Verify user has access to target site
   - Check site ID format
   - Verify session is not corrupted

3. **Token not found in API calls**
   - Ensure SyncClient is using request object
   - Check session keys exist
   - Verify middleware is installed

### Logging:
All authentication events are logged with appropriate levels:
- INFO: Successful authentication, site switches
- WARNING: Missing credentials, access denied
- ERROR: API failures, system errors

## Example Workflow

```python
# User logs in via Django form
# Signal triggers sync_auth_login()

# In a view:
def inventory_view(request):
    identity = get_sync_identity(request)
    if not identity:
        return redirect('users:login')
    
    # Use identity for API calls
    operations_api = OperationsAPI(
        SyncServerClient(
            user_id=identity.user_id,
            site_id=identity.site_id
        )
    )
    
    # Get operations for current site
    operations = operations_api.list_operations(
        filters={'site_id': identity.site_id}
    )
    
    return render(request, 'inventory.html', {
        'operations': operations,
        'identity': identity
    })
```

## Benefits

1. **Seamless Integration** - Users authenticate once, get both Django and SyncServer access
2. **Centralized Identity** - All SyncServer identity data in one structured object
3. **Flexible Site Management** - Users can switch between authorized sites
4. **Backward Compatible** - Existing code continues to work
5. **Secure** - Proper token handling and validation
6. **Extensible** - Easy to add new identity attributes