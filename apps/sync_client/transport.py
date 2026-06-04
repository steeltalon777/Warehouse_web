from __future__ import annotations

import structlog
from typing import Any

import httpx
from django.conf import settings

logger = structlog.get_logger()

_client: httpx.Client | None = None


def _build_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=getattr(settings, "SYNC_SERVER_CONNECT_TIMEOUT", 10),
        read=getattr(settings, "SYNC_SERVER_READ_TIMEOUT", 10),
        write=getattr(settings, "SYNC_SERVER_WRITE_TIMEOUT", 10),
        pool=getattr(settings, "SYNC_SERVER_POOL_TIMEOUT", 10),
    )


def get_sync_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=_build_timeout(),
        )
        logger.info("created_http_client")
    return _client


def close_sync_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        _client.close()
        logger.info("closed_http_client")
    _client = None


def replace_sync_client(client: httpx.Client | None) -> None:
    global _client
    if _client is not None and not _client.is_closed:
        _client.close()
    _client = client


IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def should_retry(method: str, response: httpx.Response | None, error: Exception | None) -> bool:
    if method not in IDEMPOTENT_METHODS:
        return False
    if error is not None:
        return True
    if response is not None and response.status_code >= 500:
        return True
    return False


def execute_with_retry(
    request_fn: callable,
    method: str,
    *,
    retries: int = 2,
    backoff: float = 0.2,
) -> httpx.Response:
    last_error: Exception | None = None
    last_response: httpx.Response | None = None

    for attempt in range(retries + 1):
        if attempt > 0:
            delay = backoff * (2 ** (attempt - 1))
            import time as _time
            _time.sleep(delay)

        last_error = None
        last_response = None

        try:
            response = request_fn()
            if should_retry(method, response=response, error=None):
                last_response = response
                continue
            return response
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            last_error = exc
            if not should_retry(method, response=None, error=exc):
                raise

    if last_response is not None:
        return last_response
    if last_error is not None:
        raise last_error
    raise RuntimeError("execute_with_retry: unexpected state")