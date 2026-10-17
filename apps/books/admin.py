from django.contrib import admin

from apps.books.models import Book, BookCopy


class BookCopyInline(admin.TabularInline):
    model = BookCopy
    extra = 0
    fields = ("inventory_number", "status", "shelf_location", "qr_code")
    readonly_fields = ("qr_code",)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "category", "total_quantity",
                    "available_quantity", "shelf_location")
    list_filter = ("category", "author", "publication_year")
    search_fields = ("title", "isbn", "author__full_name", "publisher")
    inlines = [BookCopyInline]
    readonly_fields = ("total_quantity", "available_quantity", "created_at")


@admin.register(BookCopy)
class BookCopyAdmin(admin.ModelAdmin):
    list_display = ("inventory_number", "book", "status", "shelf_location")
    list_filter = ("status",)
    search_fields = ("inventory_number", "qr_code", "book__title")
