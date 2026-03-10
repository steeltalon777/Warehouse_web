from django.contrib import admin
from .models import Site, UserProfile


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "site")
    list_filter = ("role", "site")
    search_fields = ("user__username",)