from io import StringIO
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from apps.users.models import SyncUserBinding, SyncStatus

User = get_user_model()

class AuditCommandTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="audit-admin", password="x")
        self.user = User.objects.create_user(
            username="audit-user",
            date_joined=timezone.now() - timezone.timedelta(days=31),
        )

    def test_pre_scrub_mode(self):
        out = StringIO()
        call_command("audit_admin_security", "--mode=pre-scrub", stdout=out)
        self.assertIn("PRE-SCRUB", out.getvalue())

    def test_clean_exit_zero(self):
        out = StringIO()
        try:
            call_command("audit_admin_security", "--fail-on-findings", stdout=out)
            ok = True
        except SystemExit as e:
            ok = e.code == 0
        self.assertTrue(ok)

    def test_dangerous_staff_detected(self):
        s = User.objects.create_user(username="staff-danger", is_staff=True, is_superuser=False)
        p = Permission.objects.get(codename="change_user", content_type__app_label="auth")
        s.user_permissions.add(p)
        out = StringIO()
        try:
            call_command("audit_admin_security", "--fail-on-findings", stdout=out)
            raised = False
        except SystemExit:
            raised = True
        self.assertTrue(raised)

    def test_pending_is_blocker(self):
        SyncUserBinding.objects.create(
            user=self.user,
            sync_status=SyncStatus.PENDING,
            last_sync_at=timezone.now() - timezone.timedelta(seconds=301),
        )
        try:
            call_command("audit_admin_security", "--fail-on-findings", stdout=StringIO())
            raised = False
        except SystemExit:
            raised = True
        self.assertTrue(raised)

    def test_no_uuid_in_output(self):
        import re
        out = StringIO()
        try:
            call_command("audit_admin_security", "--fail-on-findings", stdout=out)
        except SystemExit:
            pass
        uuid_pat = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
        self.assertFalse(uuid_pat.search(out.getvalue()), "No UUID tokens in output")
