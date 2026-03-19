"""
Catalog API client module for SyncServer catalog endpoints.

This module provides high-level methods for interacting with SyncServer
catalog API using the base SyncServerClient.

The module separates public read operations from admin write operations
and supports filtering for list methods.

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.catalogclient import SyncServerClient
"""

from __future__ import annotations

from .client import SyncServerClient


class CatalogAPI:
    def __init__(self, client: SyncServerClient):
        self.client = client

    # ---------- READ (web clients) ----------

    def list_items(self, *, updated_after=None, limit: int = 500):
        response = self.client.post(
            "/business/catalog/items",
            json={"updated_after": updated_after, "limit": limit},
        )
        return response.get("items", [])

    def list_categories(self, *, updated_after=None, limit: int = 500):
        response = self.client.post(
            "/business/catalog/categories",
            json={"updated_after": updated_after, "limit": limit},
        )
        return response.get("categories", [])

    def list_units(self, *, updated_after=None, limit: int = 500):
        response = self.client.post(
            "/business/catalog/units",
            json={"updated_after": updated_after, "limit": limit},
        )
        return response.get("units", [])

    def categories_tree(self):
        return self.client.get("/business/catalog/categories/tree")

    # ---------- WRITE (admin UI) ----------

    def create_item(self, payload: dict):
        return self.client.post("/catalog/admin/items", json=payload)

    def update_item(self, item_id: str, payload: dict):
        return self.client.patch(f"/catalog/admin/items/{item_id}", json=payload)

    def create_category(self, payload: dict):
        return self.client.post("/catalog/admin/categories", json=payload)

    def update_category(self, category_id: str, payload: dict):
        return self.client.patch(f"/catalog/admin/categories/{category_id}", json=payload)

    def create_unit(self, payload: dict):
        return self.client.post("/catalog/admin/units", json=payload)

    def update_unit(self, unit_id: str, payload: dict):
        return self.client.patch(f"/catalog/admin/units/{unit_id}", json=payload)