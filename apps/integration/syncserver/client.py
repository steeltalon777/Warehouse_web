import httpx
from django.conf import settings


class SyncServerClient:

    def __init__(self):
        self.base_url = settings.SYNCSERVER_API_URL.rstrip("/")

    def get_categories(self):
        url = f"{self.base_url}/catalog/categories"

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)

        response.raise_for_status()
        return response.json()