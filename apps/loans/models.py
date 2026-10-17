"""Kitob berish/qaytarish operatsiyalari (loans jadvali) va bron qilish."""
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.books.models import BookCopy, CopyStatus


class LoanStatus(models.TextChoices):
    ISSUED = "issued", "Berilgan"
    RETURNED = "returned", "Qaytarilgan"
    OVERDUE = "overdue", "Muddati o'tgan"
    LOST = "lost", "Yo'qolgan"


class Loan(models.Model):
    """ER: loans (id, reader_id, copy_id, issue_date, due_date, return_date,
    status, issued_by, created_at)."""

    reader = models.ForeignKey(
        "readers.Reader", verbose_name="Kitobxon", on_delete=models.PROTECT,
        related_name="loans",
    )
    copy = models.ForeignKey(
        BookCopy, verbose_name="Nusxa", on_delete=models.PROTECT, related_name="loans"
    )
    issue_date = models.DateField("Berilgan sana", default=timezone.localdate)
    due_date = models.DateField("Qaytarish muddati")
    return_date = models.DateField("Qaytarilgan sana", null=True, blank=True)
    status = models.CharField(
        "Holat", max_length=16, choices=LoanStatus.choices, default=LoanStatus.ISSUED
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Bergan xodim",
        on_delete=models.SET_NULL,
        null=True,
        related_name="issued_loans",
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Qabul qilgan xodim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_loans",
    )
    note = models.CharField("Izoh", max_length=255, blank=True)
    created_at = models.DateTimeField("Yaratilgan", default=timezone.now)

    class Meta:
        db_table = "loans"
        verbose_name = "Operatsiya"
        verbose_name_plural = "Berish/qaytarish operatsiyalari"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return f"{self.reader.full_name} -> {self.copy.inventory_number}"

    # -- Holat yordamchilari -------------------------------------------------
    @property
    def is_active(self):
        return self.return_date is None

    @property
    def is_overdue(self):
        return self.is_active and self.due_date < timezone.localdate()

    @property
    def days_left(self):
        return (self.due_date - timezone.localdate()).days

    @property
    def overdue_days(self):
        if not self.is_overdue:
            return 0
        return (timezone.localdate() - self.due_date).days

    def effective_status(self):
        """Joriy sanaga qarab haqiqiy holat."""
        if self.status == LoanStatus.LOST:
            return LoanStatus.LOST
        if self.return_date:
            return LoanStatus.RETURNED
        if self.is_overdue:
            return LoanStatus.OVERDUE
        return LoanStatus.ISSUED

    def save(self, *args, **kwargs):
        if not self.due_date:
            from apps.core.models import SystemSetting

            self.due_date = self.issue_date + timedelta(
                days=SystemSetting.loan_days()
            )
        if self.status != LoanStatus.LOST:
            self.status = self.effective_status()
        super().save(*args, **kwargs)

    # -- Asosiy biznes amallari ---------------------------------------------
    @classmethod
    @transaction.atomic
    def issue(cls, reader, copy, user=None, days=None, note=""):
        """Kitob nusxasini kitobxonga berish (ishlash algoritmi, 7-bo'lim)."""
        from apps.core.models import AuditLog, SystemSetting

        copy = BookCopy.objects.select_for_update().get(pk=copy.pk)
        if copy.status != CopyStatus.AVAILABLE:
            raise ValueError(
                f"Nusxa ({copy.inventory_number}) hozir mavjud emas: "
                f"{copy.get_status_display()}"
            )
        if not reader.can_borrow:
            raise ValueError(
                f"{reader.full_name} hozir kitob ololmaydi "
                "(limit to'lgan, muddati o'tgan kitob bor yoki bloklangan)."
            )

        days = days or SystemSetting.loan_days()
        today = timezone.localdate()
        loan = cls.objects.create(
            reader=reader,
            copy=copy,
            issue_date=today,
            due_date=today + timedelta(days=days),
            status=LoanStatus.ISSUED,
            issued_by=user,
            note=note,
        )
        copy.status = CopyStatus.ISSUED
        copy.save(update_fields=["status"])
        copy.book.recalc_quantities()

        AuditLog.log(
            user=user,
            action=AuditLog.Action.ISSUE,
            entity_type="loan",
            entity_id=loan.pk,
            details=f"{reader.full_name} ga '{copy.book.title}' berildi "
                    f"({copy.inventory_number}), muddat: {loan.due_date}",
        )
        return loan

    @transaction.atomic
    def give_back(self, user=None, condition=CopyStatus.AVAILABLE, note=""):
        """Kitobni qaytarib olish."""
        from apps.core.models import AuditLog

        if self.return_date:
            raise ValueError("Bu operatsiya allaqachon yopilgan.")

        self.return_date = timezone.localdate()
        self.received_by = user
        self.status = LoanStatus.LOST if condition == CopyStatus.LOST else LoanStatus.RETURNED
        if note:
            self.note = note
        self.save()

        copy = self.copy
        copy.status = condition
        copy.save(update_fields=["status"])
        copy.book.recalc_quantities()

        AuditLog.log(
            user=user,
            action=AuditLog.Action.RETURN,
            entity_type="loan",
            entity_id=self.pk,
            details=f"{self.reader.full_name} '{copy.book.title}' kitobini qaytardi "
                    f"({copy.inventory_number}), kechikish: {self.overdue_days} kun",
        )
        return self

    @transaction.atomic
    def extend(self, days=7, user=None):
        """Qaytarish muddatini uzaytirish."""
        from apps.core.models import AuditLog

        if self.return_date:
            raise ValueError("Yopilgan operatsiya muddatini uzaytirib bo'lmaydi.")
        old_due = self.due_date
        self.due_date = self.due_date + timedelta(days=days)
        self.save()
        AuditLog.log(
            user=user,
            action=AuditLog.Action.UPDATE,
            entity_type="loan",
            entity_id=self.pk,
            details=f"Muddat uzaytirildi: {old_due} -> {self.due_date}",
        )
        return self


class Reservation(models.Model):
    """Kitobxon tomonidan kitobga buyurtma (ixtiyoriy modul)."""

    class Status(models.TextChoices):
        WAITING = "waiting", "Navbatda"
        READY = "ready", "Tayyor"
        DONE = "done", "Berilgan"
        CANCELLED = "cancelled", "Bekor qilingan"

    reader = models.ForeignKey(
        "readers.Reader", verbose_name="Kitobxon", on_delete=models.CASCADE,
        related_name="reservations",
    )
    book = models.ForeignKey(
        "books.Book", verbose_name="Kitob", on_delete=models.CASCADE,
        related_name="reservations",
    )
    status = models.CharField(
        "Holat", max_length=16, choices=Status.choices, default=Status.WAITING
    )
    created_at = models.DateTimeField("Yaratilgan", default=timezone.now)

    class Meta:
        db_table = "reservations"
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.reader.full_name} -> {self.book.title}"
