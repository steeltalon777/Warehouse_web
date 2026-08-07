"""TZ-AGENT_ROLE_ADMIN_UI: agent (LLM) role assignment through Django admin.

Level 2-4: Unit + component + DB-backed integration tests covering:

A. ``Role.AGENT`` enum presence and value (TZ §6.1.A).
B. ``MANAGED_ROLE_CHOICES`` exposes agent for the dropdown (TZ §6.1.B).
C. ``SyncManagedUserAdminForm.clean()`` accepts empty ``site_ids`` for agent
   and still rejects them for non-agent roles (TZ §6.1.C).
D. Django Admin add-user POST with role=agent → binding with
   ``sync_role="agent"`` (TZ §6.1.D).
E. Django Admin change-user POST converting role=storekeeper → agent
   (TZ §6.1.E).
F. ``UserSyncService.prepare_sync`` and ``sync_user_to_remote`` emit
   ``role=agent``, ``default_site_id=null``, empty scopes payload
   (TZ §6.1.F).
G. ``apps.common.permissions.is_agent`` returns True only for agent-bound
   users (TZ §3.3.D).
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.admin_forms import (
    MANAGED_ROLE_CHOICES,
    SyncManagedUserAdminForm,
    SyncManagedUserCreationForm,
)
from apps.users.models import Role, SyncUserBinding

User = get_user_model()


# ──────────────────────────────────────────────────────────────────────
# A. Role enum
# ──────────────────────────────────────────────────────────────────────


class RoleEnumTests(TestCase):
    """A. ``Role.AGENT`` is present and has the canonical value/label."""

    def test_agent_value(self):
        self.assertEqual(Role.AGENT, "agent")

    def test_agent_label(self):
        self.assertEqual(Role.AGENT.label, "LLM Agent")

    def test_agent_in_choices(self):
        # ``Role.choices`` is a list of tuples; ``agent`` must be among them.
        values = [value for value, _ in Role.choices]
        self.assertIn(Role.AGENT, values)


# ──────────────────────────────────────────────────────────────────────
# B. MANAGED_ROLE_CHOICES
# ──────────────────────────────────────────────────────────────────────


class ManagedRoleChoicesTests(TestCase):
    """B. Admin dropdown exposes agent; root stays excluded by design."""

    def test_agent_in_managed_role_choices(self):
        values = [value for value, _ in MANAGED_ROLE_CHOICES]
        self.assertIn(Role.AGENT, values)

    def test_agent_label_in_managed_role_choices(self):
        # Human-readable label must be the Cyrillic form used in admin UI.
        agent_entry = next(
            entry for entry in MANAGED_ROLE_CHOICES if entry[0] == Role.AGENT
        )
        self.assertEqual(agent_entry[1], "LLM-агент")

    def test_root_excluded_from_managed_role_choices(self):
        values = [value for value, _ in MANAGED_ROLE_CHOICES]
        self.assertNotIn(Role.ROOT, values)


# ──────────────────────────────────────────────────────────────────────
# C. SyncManagedUserAdminForm.clean() — agent exception
# ──────────────────────────────────────────────────────────────────────


@patch.object(SyncManagedUserAdminForm, "site_choices", [("1", "WH-1"), ("2", "WH-2")])
@patch("apps.users.admin_forms.UserSyncService")
class AgentCleanTests(TestCase):
    """C. clean() accepts empty site_ids for agent; rejects for others."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="agent-clean-user", password="pw12345"
        )

    def _make_form(self, mock_svc, *, role: str, site_ids: list[str]):
        mock_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH-1", "is_active": True},
            {"site_id": 2, "name": "WH-2", "is_active": True},
        ]
        return SyncManagedUserAdminForm(
            instance=self.user,
            data={
                "username": self.user.username,
                "email": "agent@test.com",
                "full_name": "",
                "sync_role": role,
                "site_ids": site_ids,
                "is_active": True,
            },
        )

    def test_agent_with_empty_site_ids_is_valid(self, mock_svc_cls):
        form = self._make_form(mock_svc_cls, role=Role.AGENT, site_ids=[])
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")
        self.assertIsNone(form._desired_intent["default_site_id"])
        self.assertEqual(form._desired_intent["site_ids"], [])

    def test_agent_with_site_ids_uses_first_as_default(self, mock_svc_cls):
        form = self._make_form(mock_svc_cls, role=Role.AGENT, site_ids=["1", "2"])
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")
        self.assertEqual(form._desired_intent["default_site_id"], "1")
        self.assertEqual(form._desired_intent["site_ids"], ["1", "2"])

    def test_observer_with_empty_site_ids_fails(self, mock_svc_cls):
        form = self._make_form(mock_svc_cls, role=Role.OBSERVER, site_ids=[])
        self.assertFalse(form.is_valid())
        self.assertIn("выбрать хотя бы один склад", str(form.errors).lower())

    def test_storekeeper_with_empty_site_ids_fails(self, mock_svc_cls):
        # Regression: non-agent roles still require at least one site.
        form = self._make_form(mock_svc_cls, role=Role.STOREKEEPER, site_ids=[])
        self.assertFalse(form.is_valid())
        self.assertIn("выбрать хотя бы один склад", str(form.errors).lower())

    def test_root_still_rejected_via_clean(self, mock_svc_cls):
        # Root remains excluded by the existing ValidationError, regardless
        # of site_ids.
        form = self._make_form(mock_svc_cls, role=Role.ROOT, site_ids=["1"])
        self.assertFalse(form.is_valid())
        self.assertIn("root", str(form.errors).lower())


# ──────────────────────────────────────────────────────────────────────
# D. Admin add-user POST with role=agent
# ──────────────────────────────────────────────────────────────────────


@patch("apps.users.admin.UserSyncService")
@patch("apps.users.services.UserSyncService")
@patch("apps.users.admin_forms.UserSyncService")
class AdminAddAgentUserTests(TestCase):
    """D. Django Admin POST add-user with role=agent.

    The remote sync runs inside ``transaction.on_commit`` and is verified by
    unit tests in TZ §6.1.F (SyncUserPayloadForAgentTests). This test
    focuses on local Django state and form processing.
    """

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="add-agent-admin", password="AdminPass123",
        )

    def test_add_user_form_dropdown_contains_agent(self, mock_form_svc, mock_services_svc, mock_admin_svc):
        mock_form_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH-1", "is_active": True},
        ]
        mock_admin_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH-1", "is_active": True},
        ]
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:auth_user_add"))
        self.assertEqual(response.status_code, 200)
        # Role.AGENT must appear in the rendered ``sync_role`` <select>.
        self.assertContains(response, 'value="agent"')

    def test_post_add_agent_user_with_empty_sites(self, mock_form_svc, mock_services_svc, mock_admin_svc):
        mock_form_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH-1", "is_active": True},
        ]
        mock_admin_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH-1", "is_active": True},
        ]
        # The remote sync call is mocked — we only verify local Django state.
        mock_admin_svc.return_value.sync_user_to_remote.return_value = None

        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("admin:auth_user_add"),
            {
                "username": "llm_agent_smoke",
                "email": "agent-smoke@test.com",
                "password": "AgentPass123",
                "password_confirm": "AgentPass123",
                "full_name": "Agent Smoke",
                "sync_role": Role.AGENT,
                "site_ids": [],
                "is_active": "on",
                "_save": "Save",
            },
        )
        # Successful save → 302 redirect to the change page.
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="llm_agent_smoke")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

        binding = SyncUserBinding.objects.get(user=user)
        self.assertEqual(binding.sync_role, Role.AGENT)
        # site_ids default to empty list when agent has no sites.
        self.assertEqual(binding.site_ids, [])
        self.assertIsNone(binding.default_site_id)
        # Note: ``sync_user_to_remote`` runs inside ``transaction.on_commit``
        # and is hard to verify in a TestCase without plumbing through
        # CaptureQueriesContext + captureOnCommitCallbacks. The local Django
        # state (User + SyncUserBinding) is verified above. End-to-end
        # verification of the remote call is covered by TZ §6.1.F
        # (SyncUserPayloadForAgentTests) and the stand smoke (TZ §6.3).


# ──────────────────────────────────────────────────────────────────────
# E. Admin change-user POST converting role=storekeeper → agent
# ──────────────────────────────────────────────────────────────────────


@patch("apps.users.admin.UserSyncService")
@patch("apps.users.services.UserSyncService")
@patch("apps.users.admin_forms.UserSyncService")
class AdminChangeToAgentUserTests(TestCase):
    """E. Django Admin POST change-user converting role=storekeeper → agent."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="change-agent-admin", password="AdminPass123",
        )
        self.target_user = User.objects.create_user(
            username="target-change-agent", password="pw12345",
        )
        self.binding = SyncUserBinding.objects.create(
            user=self.target_user,
            sync_role=Role.STOREKEEPER,
            default_site_id="1",
            site_ids=["1"],
        )

    def test_change_role_to_agent_with_empty_sites(
        self, mock_form_svc, mock_services_svc, mock_admin_svc
    ):
        mock_form_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH-1", "is_active": True},
        ]
        mock_admin_svc.return_value.list_sites.return_value = [
            {"site_id": 1, "name": "WH-1", "is_active": True},
        ]
        mock_admin_svc.return_value.sync_user_to_remote.return_value = None

        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("admin:auth_user_change", args=[self.target_user.pk]),
            {
                "username": self.target_user.username,
                "email": self.target_user.email,
                "full_name": "Now Agent",
                "sync_role": Role.AGENT,
                "site_ids": [],
                "is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.binding.refresh_from_db()
        self.assertEqual(self.binding.sync_role, Role.AGENT)
        self.assertEqual(self.binding.site_ids, [])
        # Note: see note in ``AdminAddAgentUserTests.test_post_add_agent_user_with_empty_sites``
        # about ``transaction.on_commit``-deferred remote sync verification.


# ──────────────────────────────────────────────────────────────────────
# F. UserSyncService payload for agent
# ──────────────────────────────────────────────────────────────────────


class SyncUserPayloadForAgentTests(TestCase):
    """F. ``prepare_sync`` / ``sync_user_to_remote`` emit agent-shaped payload."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="payload-agent-admin", password="AdminPass123",
        )
        self.agent_user = User.objects.create_user(
            username="payload-agent-user", password="pw12345",
        )

    def test_prepare_sync_payload_for_agent(self):
        from apps.users.services import UserSyncService

        service = UserSyncService()
        with patch.object(service, "client") as mock_client:
            mock_client.post.return_value = {
                "user": {"user_token": "tok-agent", "default_site_id": None},
            }
            mock_client.put.return_value = {"scopes": []}
            mock_client.get.return_value = {
                "user": {"user_token": "tok-agent", "default_site_id": None},
                "scopes": [],
            }

            prepared = service.prepare_sync(
                user=self.agent_user,
                full_name="LLM Agent Payload",
                role=Role.AGENT,
                site_ids=[],
                default_site_id=None,
            )

        # POST /auth/sync-user received role=agent and default_site_id=None.
        post_call = mock_client.post.call_args_list[0]
        post_url = post_call.args[0]
        post_kwargs = post_call.kwargs
        self.assertEqual(post_url, "/auth/sync-user")
        self.assertEqual(post_kwargs["json"]["role"], Role.AGENT)
        self.assertIsNone(post_kwargs["json"]["default_site_id"])

        # PUT /admin/users/{id}/scopes received empty scopes.
        put_call = mock_client.put.call_args_list[0]
        self.assertEqual(put_call.args[0], f"/admin/users/{prepared.syncserver_user_id}/scopes")
        self.assertEqual(put_call.kwargs["json"], {"scopes": []})

    def test_sync_user_to_remote_payload_for_agent(self):
        from uuid import uuid4

        from apps.users.services import UserSyncService

        service = UserSyncService()
        binding = SyncUserBinding.objects.create(
            user=self.agent_user,
            sync_role=Role.STOREKEEPER,
            syncserver_user_id=uuid4(),
        )

        with patch.object(service, "client") as mock_client:
            mock_client.post.return_value = {
                "user": {"user_token": "tok-agent2", "default_site_id": None},
            }
            mock_client.put.return_value = {"scopes": []}
            mock_client.get.return_value = {
                "user": {"user_token": "tok-agent2", "default_site_id": None},
                "scopes": [],
            }

            service.sync_user_to_remote(
                user=self.agent_user,
                binding=binding,
                full_name="LLM Agent Remote",
                role=Role.AGENT,
                site_ids=[],
                default_site_id=None,
            )

        post_call = mock_client.post.call_args_list[0]
        self.assertEqual(post_call.args[0], "/auth/sync-user")
        self.assertEqual(post_call.kwargs["json"]["role"], Role.AGENT)
        self.assertIsNone(post_call.kwargs["json"]["default_site_id"])

        put_call = mock_client.put.call_args_list[0]
        self.assertEqual(put_call.kwargs["json"], {"scopes": []})

    def test_prepare_sync_with_normal_role_still_includes_site_in_scope(self):
        """Regression: non-agent roles still produce per-site scope entries."""
        from apps.users.services import UserSyncService

        service = UserSyncService()
        with patch.object(service, "client") as mock_client:
            mock_client.post.return_value = {
                "user": {"user_token": "tok-norm", "default_site_id": 1},
            }
            mock_client.put.return_value = {"scopes": [{"site_id": 1}]}
            mock_client.get.return_value = {
                "user": {"user_token": "tok-norm", "default_site_id": 1},
                "scopes": [{"site_id": 1}],
            }

            service.prepare_sync(
                user=self.agent_user,
                full_name="Storekeeper",
                role=Role.STOREKEEPER,
                site_ids=["1"],
                default_site_id="1",
            )

        put_call = mock_client.put.call_args_list[0]
        scopes = put_call.kwargs["json"]["scopes"]
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0]["site_id"], 1)
        self.assertTrue(scopes[0]["can_view"])
        self.assertTrue(scopes[0]["can_operate"])
        self.assertFalse(scopes[0]["can_manage_catalog"])


# ──────────────────────────────────────────────────────────────────────
# G. is_agent helper
# ──────────────────────────────────────────────────────────────────────


class IsAgentHelperTests(TestCase):
    """G. ``apps.common.permissions.is_agent`` returns True only for agent."""

    def setUp(self):
        from apps.common.permissions import is_agent

        self.is_agent = is_agent

        self.agent_bound_user = User.objects.create_user(
            username="agent-bound", password="pw12345",
        )
        SyncUserBinding.objects.create(
            user=self.agent_bound_user, sync_role=Role.AGENT,
        )

        self.storekeeper_user = User.objects.create_user(
            username="storekeeper-bound", password="pw12345",
        )
        SyncUserBinding.objects.create(
            user=self.storekeeper_user, sync_role=Role.STOREKEEPER,
        )

        self.superuser = User.objects.create_superuser(
            username="superuser-helper", password="pw12345",
        )

    def test_agent_bound_user_is_agent(self):
        self.assertTrue(self.is_agent(self.agent_bound_user))

    def test_storekeeper_bound_user_is_not_agent(self):
        self.assertFalse(self.is_agent(self.storekeeper_user))

    def test_superuser_is_not_agent(self):
        # Helper is strict: a Django superuser is root, NOT an agent.
        self.assertFalse(self.is_agent(self.superuser))

    def test_anonymous_is_not_agent(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(self.is_agent(AnonymousUser()))


# ──────────────────────────────────────────────────────────────────────
# Smoke: SyncManagedUserCreationForm (add form) inherits agent exception
# ──────────────────────────────────────────────────────────────────────


@patch.object(SyncManagedUserCreationForm, "site_choices", [("1", "WH-1")])
@patch("apps.users.admin_forms.UserSyncService")
class CreationFormAgentTests(TestCase):
    """Creation form inherits clean() and allows agent + empty sites."""

    def setUp(self):
        self.new_user = User(username="new-agent")

    def test_creation_form_accepts_agent_without_sites(self, mock_svc_cls):
        mock_svc = mock_svc_cls.return_value
        mock_svc.list_sites.return_value = [
            {"site_id": 1, "name": "WH-1", "is_active": True},
        ]
        form = SyncManagedUserCreationForm(
            data={
                "username": "new-agent",
                "email": "new-agent@test.com",
                "password": "SecretPass1",
                "password_confirm": "SecretPass1",
                "full_name": "",
                "sync_role": Role.AGENT,
                "site_ids": [],
                "is_active": True,
            },
        )
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors}")
        self.assertIsNone(form._desired_intent["default_site_id"])