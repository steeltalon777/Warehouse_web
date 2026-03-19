from __future__ import annotations

from .client import SyncServerClient


class BalancesAPI:
    def __init__(self, client: SyncServerClient):
        self.client = client

    def list(self, *, limit: int, offset: int, search: str | None = None):
        params = {"limit": limit, "offset": offset}
        if search:
            params["search"] = search
        response = self.client.get("/balances", params=params)
        return response.get("balances", response if isinstance(response, list) else [])

    def by_site(self, *, limit: int, offset: int):
        return self.client.get("/balances/by-site", params={"limit": limit, "offset": offset})

    def summary(self):
        return self.client.get("/balances/summary")
