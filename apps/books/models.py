"""Kitoblar va ularning jismoniy nusxalari (books, book_copies)."""
import uuid

from django.db import models
from django.urls import reverse
from django.utils import timezone


class CopyStatus(models.TextChoices):
    AVAILABLE = "available", "Mavjud"
    ISSUED = "issued", "Berilgan"
    LOST = "lost", "Yo'qolgan"
    DAMAGED = "damaged", "Shikastlangan"
    WRITTEN_OFF = "written_off", "Hisobdan chiqarilgan"


class Book(models.Model):
    """ER: books (id, title, author_id, category_id, isbn, publisher,
    publication_year, total_quantity, available_quantity, shelf_location,
    description, created_at)."""

    title = models.CharField("Kitob nomi", max_length=300)
    author = models.ForeignKey(
        "catalog.Author",
        verbose_name="Muallif",
        on_delete=models.PROTECT,
        related_name="books",
    )
    category = models.ForeignKey(
        "catalog.Category",
        verbose_name="Toifa",
        on_delete=models.PROTECT,
        related_name="books",
    )
    isbn = models.CharField("ISBN", max_length=20, blank=True, db_index=True)
    publisher = models.CharField("Nashriyot", max_length=200, blank=True)
    publication_year = models.PositiveIntegerField("Nashr yili", null=True, blank=True)
    total_quantity = models.PositiveIntegerField("Jami nusxa", default=0)
    available_quantity = models.PositiveIntegerField("Mavjud nusxa", default=0)
    shelf_location = models.CharField("Javon manzili", max_length=50, blank=True)
    description = models.TextField("Tavsif", blank=True)
    price = models.CharField(
        "Narxi", max_length=50, blank=True,
        help_text="Masalan: 185 200.00 yoki 'sovg'a'",
    )
    cover = models.ImageField("Muqova", upload_to="covers/", null=True, blank=True)
    created_at = models.DateTimeField("Qo'shilgan", default=timezone.now)

    class Meta:
        db_table = "books"
        verbose_name = "Kitob"
        verbose_name_plural = "Kitoblar"
        ordering = ["title"]
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["isbn"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.author.full_name}"

    def get_absolute_url(self):
        return reverse("books:detail", args=[self.pk])

    @property
    def issued_quantity(self):
        return max(self.total_quantity - self.available_quantity, 0)

    @property
    def is_available(self):
        return self.available_quantity > 0

    def recalc_quantities(self, save=True):
        """Nusxalar holatidan kelib chiqib jami/mavjud sonini qayta hisoblaydi."""
        copies = self.copies.all()
        self.total_quantity = copies.exclude(
            status__in=[CopyStatus.WRITTEN_OFF, CopyStatus.LOST]
        ).count()
        self.available_quantity = copies.filter(status=CopyStatus.AVAILABLE).count()
        if save:
            self.save(update_fields=["total_quantity", "available_quantity"])
        return self


class BookCopy(models.Model):
    """ER: book_copies (id, book_id, inventory_number, qr_code, status,
    shelf_location, created_at) - har bir jismoniy nusxa."""

    book = models.ForeignKey(
        Book, verbose_name="Kitob", on_delete=models.CASCADE, related_name="copies"
    )
    inventory_number = models.CharField("Inventar raqami", max_length=50, unique=True)
    qr_code = models.CharField("QR kod", max_length=64, blank=True, db_index=True)
    status = models.CharField(
        "Holat", max_length=16, choices=CopyStatus.choices, default=CopyStatus.AVAILABLE
    )
    shelf_location = models.CharField("Javon manzili", max_length=50, blank=True)
    note = models.CharField("Izoh", max_length=255, blank=True)
    created_at = models.DateTimeField("Qo'shilgan", default=timezone.now)

    class Meta:
        db_table = "book_copies"
        verbose_name = "Kitob nusxasi"
        verbose_name_plural = "Kitob nusxalari"
        ordering = ["inventory_number"]

    def __str__(self):
        return f"{self.inventory_number} - {self.book.title}"

    def save(self, *args, **kwargs):
        if not self.qr_code:
            self.qr_code = uuid.uuid4().hex[:16].upper()
        if not self.shelf_location and self.book_id:
            self.shelf_location = self.book.shelf_location
        super().save(*args, **kwargs)

    @property
    def is_available(self):
        return self.status == CopyStatus.AVAILABLE

    @property
    def active_loan(self):
        return self.loans.filter(return_date__isnull=True).first()
