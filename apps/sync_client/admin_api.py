from __future__ import annotations

from .client import SyncServerClient


class AdminAPI:
    def __init__(self, client: SyncServerClient):
        self.client = client

    def sites(self):
        response = self.client.get("/admin/sites")
        return response.get("sites", response if isinstance(response, list) else [])

    def devices(self):
        response = self.client.get("/admin/devices")
        return response.get("devices", response if isinstance(response, list) else [])

    def user_sites(self):
        response = self.client.get("/admin/access/user-sites")
        return response.get("access", response if isinstance(response, list) else [])
