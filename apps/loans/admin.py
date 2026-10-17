from django.contrib import admin

from apps.loans.models import Loan, Reservation


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("id", "reader", "copy", "issue_date", "due_date",
                    "return_date", "status", "issued_by")
    list_filter = ("status", "issue_date", "due_date")
    search_fields = ("reader__full_name", "reader__reader_code",
                     "copy__inventory_number", "copy__book__title")
    date_hierarchy = "issue_date"
    autocomplete_fields = ("reader", "copy")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("reader", "book", "status", "created_at")
    list_filter = ("status",)
