"""Tests for data migration 0012_scrub_sync_payload_secrets."""

from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.users.models import SyncDeviceBinding, SyncUserBinding
from apps.users.sync_contracts import assert_no_sensitive_keys

User = get_user_model()


class PayloadScrubMigrationTests(TestCase):

    def _run_migration(self):
        mod = importlib.import_module(
            "apps.users.migrations.0012_scrub_sync_payload_secrets"
        )
        mod.scrub_payloads(django_apps, None)

    def test_scrubs_user_binding_sensitive_keys(self):
        user = User.objects.create_user(username="scrub-user", password="p")
        binding = SyncUserBinding.objects.create(
            user=user,
            sync_user_token="primary-storage-token",
            last_sync_payload={
                "user_token": "secret-token",
                "scopes": [],
                "user": {
                    "user_token": "nested-token",
                    "device_token": "nested-device-token",
                    "username": "john",
                },
            },
        )

        self._run_migration()
        binding.refresh_from_db()

        assert_no_sensitive_keys(binding.last_sync_payload)
        self.assertEqual(
            binding.last_sync_payload["user"]["username"], "john"
        )

    def test_scrubs_user_binding_but_preserves_primary_token(self):
        user = User.objects.create_user(
            username="scrub-user2", password="p"
        )
        binding = SyncUserBinding.objects.create(
            user=user,
            sync_user_token="primary-token-keep",
            last_sync_payload={"user_token": "payload-token"},
        )

        self._run_migration()
        binding.refresh_from_db()

        self.assertEqual(binding.sync_user_token, "primary-token-keep")
        self.assertNotIn("user_token", binding.last_sync_payload)

    def test_scrubs_device_binding_sensitive_keys(self):
        binding = SyncDeviceBinding.objects.create(
            device_code="SCRUB-DEV-001",
            device_name="Scrub Device",
            sync_device_token="primary-device-token",
            last_sync_payload={
                "device_token": "payload-device-token",
                "device_code": "SCRUB-DEV-001",
            },
        )

        self._run_migration()
        binding.refresh_from_db()

        assert_no_sensitive_keys(binding.last_sync_payload)
        self.assertEqual(
            binding.last_sync_payload["device_code"], "SCRUB-DEV-001"
        )

    def test_scrubs_device_binding_but_preserves_primary_token(self):
        binding = SyncDeviceBinding.objects.create(
            device_code="SCRUB-DEV-002",
            device_name="Scrub Device 2",
            sync_device_token="primary-device-token-keep",
            last_sync_payload={"device_token": "payload-token"},
        )

        self._run_migration()
        binding.refresh_from_db()

        self.assertEqual(
            binding.sync_device_token, "primary-device-token-keep"
        )
        self.assertNotIn("device_token", binding.last_sync_payload)

    def test_empty_payload_not_affected(self):
        user = User.objects.create_user(
            username="scrub-user3", password="p"
        )
        binding = SyncUserBinding.objects.create(
            user=user, last_sync_payload={}
        )

        self._run_migration()
        binding.refresh_from_db()

        self.assertEqual(binding.last_sync_payload, {})

    def test_all_sensitive_keys_scrubbed_after_migration(self):
        user = User.objects.create_user(
            username="scrub-all-keys", password="p"
        )
        payload = {
            key: f"value-for-{key}"
            for key in [
                "user_token",
                "device_token",
                "sync_user_token",
                "sync_device_token",
                "authorization",
                "x-user-token",
                "x-device-token",
            ]
        }
        payload["safe_key"] = "safe-value"
        binding = SyncUserBinding.objects.create(
            user=user,
            sync_user_token="keep-primary",
            last_sync_payload=payload,
        )

        self._run_migration()
        binding.refresh_from_db()

        assert_no_sensitive_keys(binding.last_sync_payload)
        self.assertEqual(
            binding.last_sync_payload["safe_key"], "safe-value"
        )
        self.assertEqual(binding.sync_user_token, "keep-primary")
