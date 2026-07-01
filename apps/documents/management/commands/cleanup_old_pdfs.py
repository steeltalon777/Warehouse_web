from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.documents.models import RenderedDocumentArtifact


class Command(BaseCommand):
    help = "Remove PDF artifact records older than 30 days"

    def handle(self, **options):
        cutoff = timezone.now() - timedelta(days=30)
        old = RenderedDocumentArtifact.objects.filter(rendered_at__lt=cutoff)
        count = old.count()
        old.delete()
        self.stdout.write(f"Removed {count} old PDF artifact records")
