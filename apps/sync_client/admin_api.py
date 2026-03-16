from __future__ import annotations

from .client import SyncServerClient


class AdminAPI:
    def __init__(self, client: SyncServerClient):
        self.client = client

    def users(self):
        response = self.client.get("/admin/users")
        return response.get("users", response if isinstance(response, list) else [])

    def sites(self):
        response = self.client.get("/admin/sites")
        return response.get("sites", response if isinstance(response, list) else [])

    def create_site(self, payload: dict):
        return self.client.post("/admin/sites", json=payload)

    def update_site(self, site_id: str, payload: dict):
        return self.client.patch(f"/admin/sites/{site_id}", json=payload)

    def devices(self):
        response = self.client.get("/admin/devices")
        return response.get("devices", response if isinstance(response, list) else [])

    def create_device(self, payload: dict):
        return self.client.post("/admin/devices", json=payload)

    def update_device(self, device_id: str, payload: dict):
        return self.client.patch(f"/admin/devices/{device_id}", json=payload)

    def user_sites(self):
        response = self.client.get("/admin/access/user-sites")
        return response.get("access", response if isinstance(response, list) else [])

    def create_user(self, payload: dict):
        return self.client.post("/admin/users", json=payload)


    def create_user_site(self, payload: dict):
        return self.client.post("/admin/access/user-sites", json=payload)


    def update_user_site(self, payload: dict):
        return self.client.patch("/admin/access/user-sites", json=payload)


    def delete_user_site(self, payload: dict):
        return self.client.delete("/admin/access/user-sites", json=payload)