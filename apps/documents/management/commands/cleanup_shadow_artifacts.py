"""Remove expired shadow PDF artifacts older than the retention period.

Only deletes artifacts with engine='qde' and render_role='shadow' that
are older than --days.  Dry-run mode available.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.documents.models import RenderedDocumentArtifact


class Command(BaseCommand):
    help = "Remove expired shadow PDF artifacts older than --days"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Retention period in days (must be positive, default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]

        if days <= 0:
            self.stderr.write("--days must be a positive integer.")
            return

        cutoff = timezone.now() - timedelta(days=days)

        candidates = RenderedDocumentArtifact.objects.filter(
            engine="qde",
            render_role="shadow",
            created_at__lt=cutoff,
        )

        count = candidates.count()

        if dry_run:
            self.stdout.write(f"[DRY RUN] Would delete {count} expired shadow artifact(s).")
            return

        candidates.delete()
        self.stdout.write(f"Deleted {count} expired shadow artifact(s).")
