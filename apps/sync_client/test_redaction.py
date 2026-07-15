"""Tests for credential sanitizer (redaction.py)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.sync_client.redaction import sanitize_error_body, sanitize_payload


class SanitizePayloadTests(SimpleTestCase):

    def test_basic_dict_sanitization(self):
        payload = {"user_token": "secret123", "username": "john"}
        result = sanitize_payload(payload)
        self.assertNotIn("user_token", result)
        self.assertEqual(result["username"], "john")

    def test_nested_dict_sanitization(self):
        payload = {
            "user": {"user_token": "nested-token", "name": "John"},
        }
        result = sanitize_payload(payload)
        self.assertNotIn("user_token", result["user"])
        self.assertEqual(result["user"]["name"], "John")

    def test_list_of_dicts(self):
        payload = [
            {"device_token": "tok-1", "code": "DEV-1"},
            {"device_token": "tok-2", "code": "DEV-2"},
        ]
        result = sanitize_payload(payload)
        self.assertNotIn("device_token", result[0])
        self.assertEqual(result[0]["code"], "DEV-1")
        self.assertNotIn("device_token", result[1])

    def test_case_insensitive_key_matching(self):
        payload = {
            "User_Token": "val1",
            "DEVICE_TOKEN": "val2",
            "Sync_User_Token": "val3",
        }
        result = sanitize_payload(payload)
        self.assertNotIn("User_Token", result)
        self.assertNotIn("DEVICE_TOKEN", result)
        self.assertNotIn("Sync_User_Token", result)

    def test_tuple_handling(self):
        payload = ({"user_token": "secret"}, {"name": "safe"})
        result = sanitize_payload(payload)
        self.assertIsInstance(result, tuple)
        self.assertNotIn("user_token", result[0])
        self.assertEqual(result[1]["name"], "safe")

    def test_empty_input(self):
        self.assertEqual(sanitize_payload({}), {})
        self.assertEqual(sanitize_payload([]), [])
        self.assertEqual(sanitize_payload(()), ())

    def test_no_sensitive_keys_pass_through(self):
        payload = {"name": "John", "role": "admin"}
        result = sanitize_payload(payload)
        self.assertEqual(result, payload)

    def test_deep_nesting(self):
        payload = {
            "level1": {
                "level2": [
                    {"level3": {"user_token": "deep-secret"}},
                ],
            },
        }
        result = sanitize_payload(payload)
        self.assertNotIn(
            "user_token",
            result["level1"]["level2"][0]["level3"],
        )

    def test_authorization_key_redacted(self):
        payload = {"Authorization": "Bearer token123"}
        result = sanitize_payload(payload)
        self.assertNotIn("Authorization", result)


class SanitizeErrorBodyTests(SimpleTestCase):

    def test_redacts_json_key_value(self):
        text = '"user_token": "abc-def-123"'
        result = sanitize_error_body(text)
        self.assertIn("<REDACTED>", result)
        self.assertNotIn("abc-def-123", result)

    def test_redacts_colon_value(self):
        text = "user_token: secret-value"
        result = sanitize_error_body(text)
        self.assertIn("user_token: <REDACTED>", result)

    def test_redacts_equals_value(self):
        text = "user_token=abc-123-def"
        result = sanitize_error_body(text)
        self.assertIn("user_token=<REDACTED>", result)

    def test_redacts_device_token(self):
        text = "device_token: tok-456"
        result = sanitize_error_body(text)
        self.assertIn("device_token: <REDACTED>", result)

    def test_no_secrets_pass_through(self):
        text = "Everything is fine, no secrets here."
        result = sanitize_error_body(text)
        self.assertEqual(result, text)

    def test_empty_string(self):
        self.assertEqual(sanitize_error_body(""), "")

    def test_none_input(self):
        self.assertEqual(sanitize_error_body(None), "")

    def test_case_insensitive_text_redaction(self):
        text = "USER_TOKEN: some-value"
        result = sanitize_error_body(text)
        self.assertIn("USER_TOKEN: <REDACTED>", result)
