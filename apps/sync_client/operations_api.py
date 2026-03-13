from __future__ import annotations

from .client import SyncServerClient


class OperationsAPI:
    def __init__(self, client: SyncServerClient):
        self.client = client

    def list(self, *, limit: int, offset: int, search: str | None = None):
        params = {"limit": limit, "offset": offset}
        if search:
            params["search"] = search
        response = self.client.get("/operations", params=params)
        return response.get("operations", response if isinstance(response, list) else [])

    def get(self, operation_id: str):
        return self.client.get(f"/operations/{operation_id}")

    def create(self, payload: dict):
        return self.client.post("/operations", json=payload)

    def update(self, operation_id: str, payload: dict):
        return self.client.patch(f"/operations/{operation_id}", json=payload)

    def submit(self, operation_id: str):
        return self.client.post(f"/operations/{operation_id}/submit")

    def cancel(self, operation_id: str):
        return self.client.post(f"/operations/{operation_id}/cancel")
