import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.test import Client

c = Client(HTTP_HOST='127.0.0.1')
for p in ['/bff/api/v1/', '/bff/api/v1/db-check', '/bff/api/v1/health']:
    r = c.get(p)
    print(f'{p} -> {r.status_code}')
    if r.status_code == 200:
        try:
            data = r.json()
            print(f'  ok={data.get(\"ok\")}')
        except Exception:
            print('  (non-json)')
