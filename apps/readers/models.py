"""Kitobxonlar (readers jadvali)."""
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class ReaderType(models.TextChoices):
    STUDENT = "student", "Talaba / O'quvchi"
    TEACHER = "teacher", "O'qituvchi"
    EMPLOYEE = "employee", "Xodim"
    OTHER = "other", "Boshqa"


class ReaderStatus(models.TextChoices):
    ACTIVE = "active", "Faol"
    BLOCKED = "blocked", "Bloklangan"
    ARCHIVED = "archived", "Arxivlangan"


class Reader(models.Model):
    """ER: readers (id, full_name, reader_code, phone, email, reader_type,
    registration_date, status)."""

    full_name = models.CharField("F.I.Sh.", max_length=200)
    reader_code = models.CharField("Kitobxon kodi", max_length=32, unique=True)
    phone = models.CharField("Telefon", max_length=32, blank=True)
    email = models.EmailField("Email", blank=True)
    address = models.CharField("Manzil", max_length=255, blank=True)
    reader_type = models.CharField(
        "Turi", max_length=16, choices=ReaderType.choices, default=ReaderType.STUDENT
    )
    registration_date = models.DateField("Ro'yxatga olingan", default=timezone.localdate)
    status = models.CharField(
        "Holat", max_length=16, choices=ReaderStatus.choices, default=ReaderStatus.ACTIVE
    )
    note = models.TextField("Izoh", blank=True)
    # Kitobxon o'z shaxsiy kabinetiga kira olishi uchun (ixtiyoriy)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Tizim foydalanuvchisi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reader_profile",
    )

    class Meta:
        db_table = "readers"
        verbose_name = "Kitobxon"
        verbose_name_plural = "Kitobxonlar"
        ordering = ["full_name"]
        indexes = [models.Index(fields=["reader_code"]), models.Index(fields=["full_name"])]

    def __str__(self):
        return f"{self.full_name} ({self.reader_code})"

    def get_absolute_url(self):
        return reverse("readers:detail", args=[self.pk])

    @classmethod
    def generate_code(cls):
        """Keyingi bo'sh kitobxon kodini yaratadi: KX-000123."""
        last = cls.objects.order_by("-id").first()
        next_id = (last.id + 1) if last else 1
        code = f"KX-{next_id:06d}"
        while cls.objects.filter(reader_code=code).exists():
            next_id += 1
            code = f"KX-{next_id:06d}"
        return code

    @property
    def active_loans(self):
        return self.loans.filter(return_date__isnull=True)

    @property
    def active_loans_count(self):
        return self.active_loans.count()

    @property
    def overdue_loans_count(self):
        return self.active_loans.filter(due_date__lt=timezone.localdate()).count()

    @property
    def can_borrow(self):
        from apps.core.models import SystemSetting

        if self.status != ReaderStatus.ACTIVE:
            return False
        if self.overdue_loans_count > 0:
            return False
        return self.active_loans_count < SystemSetting.max_books_per_reader()
