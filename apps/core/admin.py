from django.contrib import admin

from apps.core.models import AuditLog, SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description")
    search_fields = ("key", "value")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "entity_type", "entity_id")
    list_filter = ("action", "entity_type")
    search_fields = ("details",)
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False
