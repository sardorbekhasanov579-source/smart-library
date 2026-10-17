from django.contrib import admin

from apps.readers.models import Reader


@admin.register(Reader)
class ReaderAdmin(admin.ModelAdmin):
    list_display = ("reader_code", "full_name", "reader_type", "phone",
                    "status", "registration_date")
    list_filter = ("status", "reader_type", "registration_date")
    search_fields = ("full_name", "reader_code", "phone", "email")
