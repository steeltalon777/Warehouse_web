"""Tests for sync contracts (sync_contracts.py)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.users.sync_contracts import (
    FORBIDDEN_PAYLOAD_KEYS,
    REQUIRED_DEVICE_FIELDS,
    REQUIRED_SYNC_STATE_FIELDS,
    REQUIRED_USER_FIELDS,
    assert_no_sensitive_keys,
    validate_sync_response,
)


class ValidateSyncResponseTests(SimpleTestCase):

    def test_valid_sync_state_response(self):
        response = {"user": {"id": "1"}, "scopes": []}
        self.assertTrue(
            validate_sync_response(response, REQUIRED_SYNC_STATE_FIELDS)
        )

    def test_missing_field_returns_false(self):
        response = {"user": {"id": "1"}}
        self.assertFalse(
            validate_sync_response(response, REQUIRED_SYNC_STATE_FIELDS)
        )

    def test_empty_dict_returns_false(self):
        self.assertFalse(validate_sync_response({}, REQUIRED_SYNC_STATE_FIELDS))

    def test_none_returns_false(self):
        self.assertFalse(
            validate_sync_response(None, REQUIRED_SYNC_STATE_FIELDS)
        )

    def test_valid_user_fields(self):
        response = {
            "user_token": "tok",
            "id": "1",
            "username": "john",
            "role": "storekeeper",
            "default_site_id": "1",
        }
        self.assertTrue(validate_sync_response(response, REQUIRED_USER_FIELDS))

    def test_valid_device_fields(self):
        response = {
            "device_id": 1,
            "device_code": "DEV-001",
            "device_token": "tok",
        }
        self.assertTrue(
            validate_sync_response(response, REQUIRED_DEVICE_FIELDS)
        )


class AssertNoSensitiveKeysTests(SimpleTestCase):

    def test_clean_payload_passes(self):
        payload = {"name": "John", "scopes": [], "user": {"id": "1"}}
        assert_no_sensitive_keys(payload)

    def test_sensitive_key_at_top_level_raises(self):
        payload = {"user_token": "secret", "name": "John"}
        with self.assertRaises(AssertionError):
            assert_no_sensitive_keys(payload)

    def test_sensitive_key_nested_raises(self):
        payload = {"user": {"user_token": "secret"}}
        with self.assertRaises(AssertionError):
            assert_no_sensitive_keys(payload)

    def test_sensitive_key_in_list_raises(self):
        payload = {"items": [{"device_token": "secret"}]}
        with self.assertRaises(AssertionError):
            assert_no_sensitive_keys(payload)

    def test_sync_user_token_in_primary_field_not_wiped(self):
        payload = {"name": "John"}
        assert_no_sensitive_keys(payload)
        self.assertEqual(payload.get("sync_user_token"), None)

    def test_forbidden_keys_constant_matches_redaction(self):
        self.assertIn("user_token", FORBIDDEN_PAYLOAD_KEYS)
        self.assertIn("device_token", FORBIDDEN_PAYLOAD_KEYS)
        self.assertIn("sync_user_token", FORBIDDEN_PAYLOAD_KEYS)
        self.assertIn("sync_device_token", FORBIDDEN_PAYLOAD_KEYS)
        self.assertIn("authorization", FORBIDDEN_PAYLOAD_KEYS)
        self.assertIn("x-user-token", FORBIDDEN_PAYLOAD_KEYS)
        self.assertIn("x-device-token", FORBIDDEN_PAYLOAD_KEYS)
