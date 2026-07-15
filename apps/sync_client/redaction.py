"""Credential sanitizer for SyncServer diagnostic payloads and logs.

Case-insensitive key redaction: removes sensitive keys and their values
from dicts, lists, tuples, and text without mutating the input object.
"""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS: list[str] = [
    "user_token",
    "device_token",
    "sync_user_token",
    "sync_device_token",
    "authorization",
    "x-user-token",
    "x-device-token",
]


def _key_matches(key: str, sensitive_keys: list[str]) -> bool:
    key_lower = key.lower()
    return any(sk.lower() == key_lower for sk in sensitive_keys)


def sanitize_payload(
    payload: Any,
    sensitive_keys: list[str] | None = None,
) -> Any:
    """Recursively sanitize dict/list/tuple/text by removing sensitive keys.

    Returns a new object; never mutates the input.
    Handles nested dicts, lists of dicts, tuples.
    """
    if sensitive_keys is None:
        sensitive_keys = SENSITIVE_KEYS

    if isinstance(payload, dict):
        return {
            k: sanitize_payload(v, sensitive_keys)
            for k, v in payload.items()
            if not _key_matches(k, sensitive_keys)
        }
    if isinstance(payload, list):
        return [sanitize_payload(item, sensitive_keys) for item in payload]
    if isinstance(payload, tuple):
        return tuple(sanitize_payload(item, sensitive_keys) for item in payload)
    if isinstance(payload, str):
        return sanitize_error_body(payload, sensitive_keys)
    return payload


def sanitize_error_body(
    text: str,
    sensitive_keys: list[str] | None = None,
) -> str:
    """Sanitize a text error body by removing known sensitive patterns."""
    if not isinstance(text, str):
        if text is None:
            return ""
        return str(text)
    if sensitive_keys is None:
        sensitive_keys = SENSITIVE_KEYS

    result: str = text
    for key in sensitive_keys:
        esc = re.escape(key)
        result = re.sub(
            rf'(?i)(["\']?{esc}["\']?\s*[:=]\s*["\']?)[^"\'\s,}}]+',
            r'\1<REDACTED>',
            result,
        )
    return result
