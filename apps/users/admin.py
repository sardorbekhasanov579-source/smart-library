from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.users.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "full_name", "role", "status", "created_at")
    list_filter = ("role", "status")
    search_fields = ("username", "full_name", "email")
    ordering = ("full_name",)
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Shaxsiy ma'lumot", {"fields": ("full_name", "email", "phone")}),
        ("Huquqlar", {"fields": ("role", "status", "is_staff", "is_superuser",
                                 "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "full_name", "role", "password1", "password2"),
        }),
    )
