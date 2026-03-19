# Django Views Using SyncServer API Only

## Overview

This document describes the new Django views that interact exclusively with SyncServer API without using Django ORM. These views follow the API-first architecture where all data operations go through SyncServer.

## Views Implemented

### USERS Management Views:

1. **`APIUsersView`** - List all users
   - **URL:** `/admin_panel/api/users/`
   - **Method:** `UsersAPI.list_users()`
   - **Template:** `admin_panel/users.html`
   - **Flow:** Fetch users list → Handle errors → Render template

2. **`APIUserDetailView`** - View user details
   - **URL:** `/admin_panel/api/users/<user_id>/`
   - **Method:** `UsersAPI.get_user(user_id)`
   - **Template:** `admin_panel/user_detail.html`
   - **Flow:** Fetch user details → Handle 404 → Render template

3. **`APICreateUserView`** - Create new user
   - **URL:** `/admin_panel/api/users/create/`
   - **Method:** `UsersAPI.create_user(payload)`
   - **Template:** `admin_panel/user_form.html`
   - **Flow:** Display form → Validate → Create via API → Redirect

4. **`APIUpdateUserView`** - Update existing user
   - **URL:** `/admin_panel/api/users/<user_id>/edit/`
   - **Method:** `UsersAPI.update_user(user_id, payload)`
   - **Template:** `admin_panel/user_form.html`
   - **Flow:** Fetch user → Display form → Validate → Update via API → Redirect

### SITES Management Views:

5. **`APISitesView`** - List all sites
   - **URL:** `/admin_panel/api/sites/`
   - **Method:** `SitesAPI.list_sites()`
   - **Template:** `admin_panel/sites.html`
   - **Flow:** Fetch sites list → Handle errors → Render template

6. **`APICreateSiteView`** - Create new site
   - **URL:** `/admin_panel/api/sites/create/`
   - **Method:** `SitesAPI.create_site(payload)`
   - **Template:** `admin_panel/site_form.html`
   - **Flow:** Display form → Validate → Create via API → Redirect

7. **`APIUpdateSiteView`** - Update existing site
   - **URL:** `/admin_panel/api/sites/<site_id>/edit/`
   - **Method:** `SitesAPI.update_site(site_id, payload)`
   - **Template:** `admin_panel/site_form.html`
   - **Flow:** Fetch site → Display form → Validate → Update via API → Redirect

## Key Design Principles

### 1. No Django ORM Queries
- All data operations go through SyncServer API
- No `User.objects.get()`, `User.objects.create()`, etc.
- Django auth is only for access control (root/admin check)

### 2. API Clients Only
- Use `UsersAPI` and `SitesAPI` clients
- Inherit from `SyncContextMixin` for client initialization
- Handle all API errors appropriately

### 3. Error Handling
- `SyncValidationError` - Form validation errors (400/422)
- `SyncNotFoundError` - Resource not found (404)
- `SyncForbiddenError` - Permission denied (403)
- `SyncAPIError` - Generic API errors
- All errors shown via `messages.error()`

### 4. Template Context
- Return structured data for templates
- Include `mode` parameter (create/update)
- Pass form data and validation errors
- Include related data (e.g., sites for user forms)

## Flow Explanation

### User Creation Flow:
```
1. GET /admin_panel/api/users/create/
   → Fetch available sites from SitesAPI
   → Render form with sites dropdown

2. POST /admin_panel/api/users/create/
   → Validate form data
   → Prepare payload for UsersAPI
   → Call UsersAPI.create_user(payload)
   → On success: redirect to users list with success message
   → On error: redisplay form with error messages
```

### User Update Flow:
```
1. GET /admin_panel/api/users/<user_id>/edit/
   → Call UsersAPI.get_user(user_id)
   → Fetch available sites from SitesAPI
   → Render form with user data and sites dropdown

2. POST /admin_panel/api/users/<user_id>/edit/
   → Validate form data
   → Prepare update payload
   → Call UsersAPI.update_user(user_id, payload)
   → On success: redirect to users list with success message
   → On error: redisplay form with error messages
```

### Site Management Flow:
Similar to user management but using `SitesAPI` instead of `UsersAPI`.

## Context Data Structure

### For List Views:
```python
context = {
    'users': [],  # or 'sites': []
    # List of dictionaries from API
}
```

### For Form Views (Create/Update):
```python
context = {
    'mode': 'create',  # or 'update'
    'form_data': {},   # Form field values
    'errors': {},      # Validation errors
    'sites': [],       # Available sites (for user forms)
    'user_id': '...',  # or 'site_id': '...' (for update)
    'user': {},        # or 'site': {} (for update - full object)
}
```

## Error Messages

### API Error Handling:
```python
try:
    users_api = UsersAPI(self.client)
    users = users_api.list_users()
except SyncNotFoundError:
    messages.error(request, "Пользователь не найден")
    raise Http404
except SyncValidationError as exc:
    messages.error(request, f"Ошибка валидации: {exc}")
except SyncAPIError as exc:
    messages.error(request, f"Ошибка API: {exc}")
except Exception as exc:
    messages.error(request, f"Неожиданная ошибка: {exc}")
```

### Form Validation Errors:
Displayed next to relevant form fields or as general errors.

## Security Considerations

### Access Control:
- All views inherit from `RootOnlyMixin`
- Requires `request.user.is_superuser`
- Protects admin functionality

### Data Validation:
- Form validation before API calls
- API validation on server side
- No direct database access

### Session Management:
- Uses `SyncContextMixin` for proper client initialization
- Maintains acting user/site context
- Follows existing authentication patterns

## Migration Path

### From Legacy Views:
1. **Legacy:** `/admin_panel/users/` (Django ORM + API mix)
2. **New:** `/admin_panel/api/users/` (API only)

### Benefits:
- Clean separation of concerns
- No Django ORM dependency for business data
- Consistent error handling
- Better scalability

### Compatibility:
- Legacy views remain functional
- New views use different URL patterns
- Gradual migration possible

## Testing Considerations

### What to Test:
1. API connectivity and error handling
2. Form validation and submission
3. Access control (root-only)
4. Template rendering with context
5. Redirect behavior

### Mocking:
- Mock `UsersAPI` and `SitesAPI` methods
- Simulate API errors
- Test error message display

## Usage Example

### In Templates:
```django
<!-- users.html -->
{% for user in users %}
  <tr>
    <td>{{ user.username }}</td>
    <td>{{ user.email }}</td>
    <td>{{ user.full_name }}</td>
    <td>
      <a href="{% url 'admin_panel:api_user_detail' user.id %}">
        Детали
      </a>
      <a href="{% url 'admin_panel:api_user_edit' user.id %}">
        Редактировать
      </a>
    </td>
  </tr>
{% endfor %}
```

### In Views (Custom):
```python
from apps.admin_panel.api_views import APICreateUserView

class CustomUserCreateView(APICreateUserView):
    """Customized user creation with additional logic."""
    
    def post(self, request):
        # Custom pre-processing
        # ...
        # Call parent implementation
        return super().post(request)
```

## Files Created/Updated

### New File:
- `apps/admin_panel/api_views.py` - All API-only views

### Updated Files:
- `apps/admin_panel/urls.py` - Added API view URLs
- `docs/api_only_views.md` - This documentation

### Templates Used:
- `admin_panel/users.html` - User list
- `admin_panel/user_detail.html` - User details
- `admin_panel/user_form.html` - User create/update form
- `admin_panel/sites.html` - Site list
- `admin_panel/site_form.html` - Site create/update form

## Conclusion

The new API-only views provide a clean, maintainable approach to user and site management that fully embraces the API-first architecture. By eliminating Django ORM dependencies and using only SyncServer API, these views ensure consistency, scalability, and proper separation of concerns.