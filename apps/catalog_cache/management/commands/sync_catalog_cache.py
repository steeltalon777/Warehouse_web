from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalog_cache.services import CatalogCacheSyncService, SYNC_SERVER_MAX_PAGE_SIZE


class Command(BaseCommand):
    help = "Sync SyncServer catalog read-cache into local Django tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--items-only",
            action="store_true",
            help="Sync only catalog items cache. Currently this is the only supported mode.",
        )
        parser.add_argument(
            "--page-size",
            type=int,
            default=SYNC_SERVER_MAX_PAGE_SIZE,
            help="Remote page size used while reading SyncServer browse items.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=None,
            help="Optional guard to stop after a fixed number of pages.",
        )

    def handle(self, *args, **options):
        requested_page_size = int(options["page_size"] or SYNC_SERVER_MAX_PAGE_SIZE)
        page_size = min(max(requested_page_size, 1), SYNC_SERVER_MAX_PAGE_SIZE)
        max_pages = options.get("max_pages")

        if page_size != requested_page_size:
            self.stdout.write(
                self.style.WARNING(
                    f"Requested page size {requested_page_size} exceeds SyncServer limit; using {page_size}."
                )
            )

        service = CatalogCacheSyncService()
        stats = service.sync_items(page_size=page_size, max_pages=max_pages)

        self.stdout.write(
            self.style.SUCCESS(
                "Catalog cache sync completed: "
                f"pages={stats.pages}, fetched={stats.fetched}, upserted={stats.upserted}, "
                f"skipped={stats.skipped}, total_count={stats.total_count}"
            )
        )
