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