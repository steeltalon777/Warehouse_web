from __future__ import annotations

from .client import SyncServerClient


class CatalogAPI:
    def __init__(self, client: SyncServerClient):
        self.client = client

    def create_item(self, payload: dict):
        return self.client.post("/business/catalog/items", json=payload)

    def create_category(self, payload: dict):
        return self.client.post("/business/catalog/categories", json=payload)

    def create_unit(self, payload: dict):
        return self.client.post("/business/catalog/units", json=payload)

    def categories_tree(self):
        return self.client.get("/business/catalog/categories/tree")
