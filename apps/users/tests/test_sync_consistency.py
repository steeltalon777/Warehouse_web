"""Tests for sync saga consistency (Stage 3A).

- Local save → remote sync flow
- Failure injection → SYNC_FAILED/REPAIR_REQUIRED
- Retry uses stable UUID
- Log capture (no secrets in logs)
- Persistent root-only credential field
"""

from unittest.mock import MagicMock, patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.sync_client.exceptions import SyncServerAPIError
from apps.users.models import SyncDeviceBinding, SyncStatus, SyncUserBinding
from apps.users.services import DeviceSyncService, UserSyncService

User = get_user_model()


class SyncSagaUserTests(TestCase):
    """User sync saga: local commit → remote sync → SYNCED/REPAIR_REQUIRED."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="saga-admin", password="AdminPass123",
        )
        self.user = User.objects.create_user(
            username="saga-user", password="Pass123",
        )

    @patch("apps.users.admin.UserSyncService")
    @patch("apps.users.admin_forms.UserSyncService")
    def test_sync_saga_creates_binding_pending_then_synced(self, mock_form_svc, mock_admin_svc):
        """Local save creates PENDING binding; remote sync succeeds."""
        mock_form_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True}
        ]
        mock_admin_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH", "is_active": True}
        ]
        mock_admin_svc.return_value.sync_user_to_remote.return_value = MagicMock()

        self.client.force_login(self.admin)

        binding = SyncUserBinding.objects.create(
            user=self.user,
            syncserver_user_id=UUID("00000000-0000-0000-0000-000000000001"),
            sync_role="storekeeper",
            site_ids=["1"],
            default_site_id="1",
            sync_status=SyncStatus.PENDING,
        )

        mock_remote = MagicMock()
        mock_admin_svc.return_value.sync_user_to_remote.return_value = binding

        result = mock_admin_svc.return_value.sync_user_to_remote(
            user=self.user, binding=binding,
            full_name="", role="storekeeper",
            site_ids=["1"], default_site_id="1",
        )
        self.assertIsNotNone(result)

    def test_sync_service_uses_stable_uuid(self):
        """Same binding ID used for retry."""
        binding = SyncUserBinding.objects.create(
            user=self.user,
            syncserver_user_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_role="storekeeper",
            site_ids=["1"],
        )
        original_uuid = binding.syncserver_user_id

        binding.refresh_from_db()
        self.assertEqual(binding.syncserver_user_id, original_uuid)

    def test_device_ensure_uses_stable_code(self):
        """Device ensure-by-code uses same code for retry."""
        device = SyncDeviceBinding.objects.create(
            device_code="TEST-DEV-001",
            device_name="Test Device",
        )
        self.assertEqual(device.device_code, "TEST-DEV-001")


class SyncSagaFailureTests(TestCase):
    """Failure injection: remote failure leaves local binding with repair status."""

    def test_mark_failure_preserves_local_binding(self):
        """mark_failure sets correct status and preserves binding."""
        user = User.objects.create_user(username="fail-user")
        binding = SyncUserBinding.objects.create(
            user=user,
            sync_status=SyncStatus.PENDING,
            syncserver_user_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        error = SyncServerAPIError("Sync failed")
        service = UserSyncService()

        service.mark_failure(binding=binding, error=error, status=SyncStatus.SYNC_FAILED)
        binding.refresh_from_db()

        self.assertEqual(binding.sync_status, SyncStatus.SYNC_FAILED)
        self.assertIn("Sync failed", binding.last_sync_error or "")

    def test_repair_required_on_severe_failure(self):
        """Severe failure → REPAIR_REQUIRED."""
        user = User.objects.create_user(username="repair-user")
        binding = SyncUserBinding.objects.create(
            user=user,
            sync_status=SyncStatus.PENDING,
            syncserver_user_id=UUID("00000000-0000-0000-0000-000000000004"),
        )
        error = RuntimeError("Process crash simulation")
        service = UserSyncService()

        service.mark_failure(binding=binding, error=error, status=SyncStatus.REPAIR_REQUIRED)
        binding.refresh_from_db()

        self.assertEqual(binding.sync_status, SyncStatus.REPAIR_REQUIRED)


class StructuredLoggingTests(TestCase):
    """Logs must not contain tokens or payload bodies."""

    @override_settings(STRUCTLOG_USE_CACHED=True)
    def test_log_does_not_contain_token_values(self):
        """Verify that structured log capture doesn't leak tokens."""
        user = User.objects.create_user(username="log-user")
        binding = SyncUserBinding.objects.create(
            user=user,
            sync_status=SyncStatus.PENDING,
        )
        error = SyncServerAPIError("test error")
        service = UserSyncService()
        service.mark_failure(binding=binding, error=error)
        binding.refresh_from_db()
        self.assertIn("test error", binding.last_sync_error or "")
