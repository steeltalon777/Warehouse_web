"""
Example usage of the new admin API clients.

This script demonstrates how to use the UsersAPI, SitesAPI, and AccessAPI
modules for admin operations.

Note: This is for demonstration purposes only. In production,
you would use these APIs within Django views or services.
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from apps.sync_client.client import SyncServerClient
from apps.sync_client.users_api import UsersAPI, get_users_api
from apps.sync_client.sites_api import SitesAPI, get_sites_api
from apps.sync_client.access_api import AccessAPI, get_access_api


def demonstrate_users_api():
    """Demonstrate UsersAPI usage."""
    print("=== UsersAPI Demo ===")
    
    # Method 1: Create client and API instance
    client = SyncServerClient(user_id="admin", site_id="main")
    users_api = UsersAPI(client)
    
    # Method 2: Use convenience function
    users_api2 = get_users_api()
    
    # List users
    try:
        users = users_api.list_users()
        print(f"Found {len(users)} users")
        for user in users[:3]:  # Show first 3 users
            print(f"  - {user.get('username', 'N/A')} ({user.get('id', 'N/A')})")
    except Exception as e:
        print(f"Error listing users: {e}")
    
    print()


def demonstrate_sites_api():
    """Demonstrate SitesAPI usage."""
    print("=== SitesAPI Demo ===")
    
    sites_api = get_sites_api()
    
    # List sites
    try:
        sites = sites_api.list_sites()
        print(f"Found {len(sites)} sites")
        for site in sites[:3]:  # Show first 3 sites
            print(f"  - {site.get('name', 'N/A')} ({site.get('code', 'N/A')})")
    except Exception as e:
        print(f"Error listing sites: {e}")
    
    print()


def demonstrate_access_api():
    """Demonstrate AccessAPI usage."""
    print("=== AccessAPI Demo ===")
    
    access_api = get_access_api()
    
    # List access records
    try:
        access_records = access_api.list_access()
        print(f"Found {len(access_records)} access records")
        for record in access_records[:3]:  # Show first 3 records
            print(f"  - User: {record.get('user_id', 'N/A')}, "
                  f"Site: {record.get('site_id', 'N/A')}, "
                  f"Role: {record.get('role', 'N/A')}")
    except Exception as e:
        print(f"Error listing access records: {e}")
    
    print()


def demonstrate_complete_workflow():
    """Demonstrate a complete admin workflow."""
    print("=== Complete Admin Workflow Demo ===")
    
    # Initialize all APIs
    users_api = get_users_api()
    sites_api = get_sites_api()
    access_api = get_access_api()
    
    print("1. Getting current users, sites, and access records...")
    
    try:
        users = users_api.list_users()
        sites = sites_api.list_sites()
        access_records = access_api.list_access()
        
        print(f"   - Users: {len(users)}")
        print(f"   - Sites: {len(sites)}")
        print(f"   - Access records: {len(access_records)}")
        
        # Show sample data
        if users:
            print(f"\n   Sample user: {users[0].get('username', 'N/A')}")
        if sites:
            print(f"   Sample site: {sites[0].get('name', 'N/A')}")
        if access_records:
            print(f"   Sample access: User {access_records[0].get('user_id', 'N/A')} "
                  f"→ Site {access_records[0].get('site_id', 'N/A')}")
        
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\nNote: Create, update, and delete operations would require valid payloads.")
    print("These are demonstrated in the API documentation.")


if __name__ == "__main__":
    print("Admin API Clients Demonstration\n")
    
    demonstrate_users_api()
    demonstrate_sites_api()
    demonstrate_access_api()
    demonstrate_complete_workflow()
    
    print("\n=== API Endpoints Used ===")
    print("UsersAPI:")
    print("  - GET    /admin/users")
    print("  - GET    /admin/users/{user_id}")
    print("  - POST   /admin/users")
    print("  - PATCH  /admin/users/{user_id}")
    print("  - DELETE /admin/users/{user_id}")
    print()
    print("SitesAPI:")
    print("  - GET    /admin/sites")
    print("  - POST   /admin/sites")
    print("  - PATCH  /admin/sites/{site_id}")
    print()
    print("AccessAPI:")
    print("  - GET    /admin/access/user-sites")
    print("  - POST   /admin/access/user-sites")
    print("  - PATCH  /admin/access/user-sites/{access_id}")
    print()
    print("All endpoints use service authentication with X-Acting-User-Id and X-Acting-Site-Id headers.")