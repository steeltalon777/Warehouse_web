from django import template

from apps.common.permissions import can_manage_catalog as user_can_manage_catalog

register = template.Library()


@register.filter(name="can_manage_catalog")
def can_manage_catalog_filter(user) -> bool:
    return user_can_manage_catalog(user)
