import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Category(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=100, blank=True, null=True)

    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.parent and self.parent_id == self.id:
            raise ValidationError("Категория не может быть родителем самой себя.")

        parent = self.parent
        while parent:
            if parent.id == self.id:
                raise ValidationError("Нельзя создать циклическую связь в дереве категорий.")
            parent = parent.parent

class Unit(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"

class Item(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(max_length=255)

    sku = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name="items",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name