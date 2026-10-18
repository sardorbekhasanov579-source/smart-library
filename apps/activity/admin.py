from django.contrib import admin

from apps.activity.models import ActivityRecord


@admin.register(ActivityRecord)
class ActivityRecordAdmin(admin.ModelAdmin):
    list_display = ("reader", "kind", "points", "happened_at", "note")
    list_filter = ("kind", "happened_at")
    search_fields = ("reader__full_name", "reader__reader_code", "note")
    date_hierarchy = "happened_at"
    readonly_fields = ("source_key",)
