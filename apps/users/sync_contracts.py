"""Sync contracts — validated response structure expectations."""

from __future__ import annotations

from typing import Any

# Required fields for user sync-state response validation
REQUIRED_SYNC_STATE_FIELDS: list[str] = ["user", "scopes"]
REQUIRED_USER_FIELDS: list[str] = [
    "user_token",
    "id",
    "username",
    "role",
    "default_site_id",
]

# Required fields for device ensure/create response
REQUIRED_DEVICE_FIELDS: list[str] = ["device_id", "device_code", "device_token"]
REQUIRED_DEVICE_ENSURE_FIELDS: list[str] = ["device_id", "device_code", "device_token"]

# Key names that MUST NOT appear in any last_sync_payload after sanitization
FORBIDDEN_PAYLOAD_KEYS: list[str] = [
    "user_token",
    "device_token",
    "sync_user_token",
    "sync_device_token",
    "authorization",
    "x-user-token",
    "x-device-token",
]


def validate_sync_response(response: dict, required_fields: list[str]) -> bool:
    """Validate that a sync response contains all required fields."""
    if not isinstance(response, dict):
        return False
    return all(field in response for field in required_fields)


def assert_no_sensitive_keys(
    payload: Any,
    forbidden_keys: list[str] | None = None,
) -> None:
    """Assert no forbidden keys exist in a payload (recursively).

    Raises AssertionError if any forbidden key is found.
    """
    if forbidden_keys is None:
        forbidden_keys = FORBIDDEN_PAYLOAD_KEYS
    _check_no_sensitive_keys(payload, forbidden_keys)


def _check_no_sensitive_keys(payload: Any, forbidden_keys: list[str]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if any(key.lower() == fk.lower() for fk in forbidden_keys):
                raise AssertionError(
                    f"Sensitive key '{key}' found in payload"
                )
            _check_no_sensitive_keys(value, forbidden_keys)
    elif isinstance(payload, list):
        for item in payload:
            _check_no_sensitive_keys(item, forbidden_keys)
    elif isinstance(payload, tuple):
        for item in payload:
            _check_no_sensitive_keys(item, forbidden_keys)
