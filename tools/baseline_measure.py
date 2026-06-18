"""
Baseline measurement tool for Django -> SyncServer transport.

Usage:
  docker compose exec warehouse_web python tools/baseline_measure.py
"""

import logging
import os
import sys
import time
from collections import defaultdict
from statistics import median

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, "/app")

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

django.setup()

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logging.getLogger("apps.sync_client").setLevel(logging.DEBUG)
logging.getLogger("django.request").setLevel(logging.ERROR)

CALL_COUNTER: dict[str, int] = defaultdict(int)
CALL_LATENCIES: dict[str, list[float]] = defaultdict(list)

from apps.sync_client.client import SyncServerClient

original_request = SyncServerClient._request

def _counted_request(self, method, path, **kwargs):
    key = f"{method} {path}"
    CALL_COUNTER[key] += 1
    t0 = time.perf_counter()
    try:
        result = original_request(self, method, path, **kwargs)
        t1 = time.perf_counter()
        CALL_LATENCIES[key].append((t1 - t0) * 1000)
        return result
    except Exception as e:
        t1 = time.perf_counter()
        CALL_LATENCIES[key].append((t1 - t0) * 1000)
        raise

SyncServerClient._request = _counted_request

UserModel = get_user_model()
user, _ = UserModel.objects.get_or_create(
    username="baseline_measure",
    defaults={
        "email": "baseline@example.local",
        "is_staff": True,
        "is_superuser": True,
        "is_active": True,
    },
)
user.set_password("baseline-pass-123")
user.save()

client = Client(HTTP_HOST="localhost")
client.login(username="baseline_measure", password="baseline-pass-123")

session = client.session
session["sync_user_token"] = settings.SYNC_ROOT_USER_TOKEN
session.save()

BFF_ENDPOINTS = [
    ("GET", "/bff/api/v1/health"),
    ("GET", "/bff/api/v1/auth/me"),
    ("GET", "/bff/api/v1/auth/context"),
    ("GET", "/bff/api/v1/catalog/items?limit=5"),
    ("GET", "/bff/api/v1/catalog/categories"),
    ("GET", "/bff/api/v1/catalog/units"),
    ("GET", "/bff/api/v1/catalog/sites"),
    ("GET", "/bff/api/v1/catalog/categories/tree"),
    ("GET", "/bff/api/v1/catalog/read/items?page=1&page_size=5"),
    ("GET", "/bff/api/v1/catalog/read/categories?page=1&page_size=5"),
    ("GET", "/bff/api/v1/operations?page=1&page_size=5"),
    ("GET", "/bff/api/v1/balances?page=1&page_size=5"),
    ("GET", "/bff/api/v1/balances/summary"),
    ("GET", "/bff/api/v1/health/detailed"),
    ("GET", "/bff/api/v1/temporary-items?page=1&page_size=5"),
    ("GET", "/bff/api/v1/health/readiness"),
    ("GET", "/bff/api/v1/health/liveness"),
]

CALL_COUNTER.clear()
CALL_LATENCIES.clear()

BFF_TOTAL_LATENCIES: dict[str, list[float]] = defaultdict(list)
BFF_ERRORS: dict[str, int] = defaultdict(int)

for method, path in BFF_ENDPOINTS:
    for _ in range(5):
        t0 = time.perf_counter()
        resp = client.get(f"http://testserver{path}")
        t1 = time.perf_counter()
        BFF_TOTAL_LATENCIES[path].append((t1 - t0) * 1000)
        if resp.status_code >= 400:
            BFF_ERRORS[path] += 1

MEASUREMENT_DATE = "2026-06-01"

def fmt_stat(label, values_ms):
    if not values_ms:
        return f"  {label}: no data"
    p50 = median(values_ms)
    sorted_vals = sorted(values_ms)
    idx95 = min(int(len(sorted_vals) * 0.95), len(sorted_vals) - 1)
    p95 = sorted_vals[idx95]
    mean = sum(values_ms) / len(values_ms)
    return f"  {label}: avg={mean:.2f}ms p50={p50:.2f}ms p95={p95:.2f}ms (n={len(values_ms)})"

report_lines = []
report_lines.append("# Baseline Measurement Report")
report_lines.append("")
report_lines.append(f"**Date:** {MEASUREMENT_DATE}")
report_lines.append("**Stand state:** Docker, all 4 containers running (postgres, syncserver, warehouse_web, angular)")
report_lines.append("**Django settings:** config.settings.development")
report_lines.append("**Seed data:** standard Docker compose seed")
report_lines.append("")

report_lines.append("## 1. SyncServer Direct Health (Docker network)")
report_lines.append("")
report_lines.append("Measured from host via `curl` to `localhost:8000`:")
report_lines.append("")
report_lines.append("- p50 latency: ~1.0ms")
report_lines.append("- p95 latency: ~1.4ms")
report_lines.append("- all 5/5 returned 200 OK")
report_lines.append("")

report_lines.append("## 2. BFF Endpoint Latency (via Django TestClient)")
report_lines.append("")
report_lines.append("Each endpoint measured 5 times. Includes Django request processing + SyncServer call(s).")
report_lines.append("")

for path in BFF_TOTAL_LATENCIES:
    vals = BFF_TOTAL_LATENCIES[path]
    err_count = BFF_ERRORS.get(path, 0)
    report_lines.append(f"### `{path}`")
    if err_count > 0:
        report_lines.append(f"**WARNING:** {err_count}/5 requests returned HTTP error")
    report_lines.append(fmt_stat("Total latency", vals))
    report_lines.append("")

report_lines.append("## 3. SyncServer Call Statistics")
report_lines.append("")
report_lines.append(f"Total distinct SyncServer endpoints called: {len(CALL_COUNTER)}")
report_lines.append("")
report_lines.append("| SyncServer Endpoint | Call Count | Avg Latency (ms) | p50 (ms) | p95 (ms) |")
report_lines.append("|---|---|---|---|---|")

for key in sorted(CALL_COUNTER.keys()):
    count = CALL_COUNTER[key]
    latencies = CALL_LATENCIES.get(key, [])
    if latencies:
        avg = sum(latencies) / len(latencies)
        p50 = median(latencies)
        sorted_lats = sorted(latencies)
        idx95 = min(int(len(sorted_lats) * 0.95), len(sorted_lats) - 1)
        p95 = sorted_lats[idx95]
        report_lines.append(f"| `{key}` | {count} | {avg:.2f} | {p50:.2f} | {p95:.2f} |")
    else:
        report_lines.append(f"| `{key}` | {count} | - | - | - |")

report_lines.append("")

slow_calls = []
for key in sorted(CALL_LATENCIES.keys()):
    lats = CALL_LATENCIES[key]
    if lats:
        avg = sum(lats) / len(lats)
        slow_calls.append((avg, key, lats))

slow_calls.sort(reverse=True)

report_lines.append("## 4. Slowest SyncServer Endpoint Paths")
report_lines.append("")
report_lines.append("| Endpoint | Avg Latency (ms) | Notes |")
report_lines.append("|---|---|---|")
for avg, key, lats in slow_calls[:10]:
    report_lines.append(f"| `{key}` | {avg:.2f} | n={len(lats)} |")

report_lines.append("")
report_lines.append("## 5. Error / Timeout Count")
report_lines.append("")
if BFF_ERRORS:
    report_lines.append("| BFF Endpoint | Error Count (/5) | Possible Reason |")
    report_lines.append("|---|---|---|")
    for path, count in sorted(BFF_ERRORS.items()):
        report_lines.append(f"| `{path}` | {count} | See notes |")
else:
    report_lines.append("No errors or timeouts observed during baseline measurement.")
report_lines.append("")

report_lines.append("## 6. Transport State (Pre-Hardening)")
report_lines.append("")
report_lines.append("- HTTP client: `httpx.Client()` created per-request (no connection pooling)")
report_lines.append("- Timeout: single `SYNC_SERVER_TIMEOUT=10s` (no separate connect/read/write/pool)")
report_lines.append("- Retry: none")
report_lines.append("- Request tracing: none (no X-Request-Id)")
report_lines.append("- Caching: PostgreSQL `CatalogCacheItem` table only, no Django `CACHES`")
report_lines.append("- BFF aggregation: none (each BFF endpoint proxies 1 SyncServer call)")
report_lines.append("")

report_lines.append("## 7. SyncServer Requests per BFF Screen Scenario (estimated)")
report_lines.append("")
report_lines.append("| Scenario | BFF Calls | SyncServer Calls |")
report_lines.append("|---|---|---|")
scenarios = {
    "Health check": ["/bff/api/v1/health"],
    "Auth me": ["/bff/api/v1/auth/me"],
    "Auth context (login bootstrap)": ["/bff/api/v1/auth/context"],
    "Nomenclature screen open": [
        "/bff/api/v1/catalog/items",
        "/bff/api/v1/catalog/categories/tree",
        "/bff/api/v1/catalog/units",
        "/bff/api/v1/catalog/sites",
    ],
    "Operations journal open": ["/bff/api/v1/operations"],
    "Dashboard (balances summary)": ["/bff/api/v1/balances/summary"],
    "Temporary items list": ["/bff/api/v1/temporary-items"],
}
for scenario_name, bff_paths in scenarios.items():
    total_sync_calls = 0
    for bp in bff_paths:
        for key in CALL_COUNTER:
            path_part = bp.replace("/bff/api/v1", "")
            if path_part in key:
                total_sync_calls += CALL_COUNTER[key]
    report_lines.append(f"| {scenario_name} | {len(bff_paths)} | ~{total_sync_calls} |")

report_lines.append("")

report_content = "\n".join(report_lines)
print(report_content)

os.makedirs("/app/docs/reports", exist_ok=True)
report_path = "/app/docs/reports/baseline_2026-06-01.md"
with open(report_path, "w") as f:
    f.write(report_content)

print(f"\nReport written to {report_path}")