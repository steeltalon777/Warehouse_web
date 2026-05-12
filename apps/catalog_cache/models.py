from __future__ import annotations

from django.db import models


class CatalogCacheItem(models.Model):
    sync_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, blank=True)
    search_text = models.TextField(blank=True)
    category_id = models.CharField(max_length=64, blank=True)
    category_name = models.CharField(max_length=255, blank=True)
    unit_symbol = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    hashtags = models.JSONField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField()

    class Meta:
        db_table = "catalog_cache_item"
        ordering = ["name", "sync_id"]
        indexes = [
            models.Index(fields=["sku"], name="catalog_cache_sku_idx"),
            models.Index(fields=["category_id"], name="catalog_cache_category_idx"),
            models.Index(fields=["is_active"], name="catalog_cache_active_idx"),
        ]

    def __str__(self) -> str:
        return self.name
