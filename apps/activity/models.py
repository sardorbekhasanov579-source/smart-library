"""Ijtimoiy faollik: kitobxonning kutubxonadagi faolligi uchun ballar.

Har bir ball alohida yozuv sifatida saqlanadi — shunda qaysi ball nima uchun
berilgani ko'rinib turadi va HEMIS kabi tashqi tizimga uzatish oson bo'ladi.

Yozuvlar ikki yo'l bilan paydo bo'ladi:
  1. `recalc_activity` komandasi — kitob berish/qaytarish va test natijalaridan
     avtomatik hisoblaydi. Takroran ishga tushsa dublikat yaratmaydi.
  2. Kutubxonachi qo'lda qo'shadi (tadbirda qatnashish, kitob sovg'a qilish va h.k.)
"""
from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone


class ActivityKind(models.TextChoices):
    BORROW = "borrow", "Kitob oldi"
    RETURN_ONTIME = "return_ontime", "Muddatida qaytardi"
    OVERDUE = "overdue", "Kechiktirib qaytardi"
    QUIZ_PASSED = "quiz_passed", "Testdan o'tdi"
    QUIZ_PERFECT = "quiz_perfect", "Testni a'lo yechdi"
    QUIZ_FAILED = "quiz_failed", "Testdan o'tolmadi"
    MANUAL = "manual", "Qo'lda berilgan"


# Qaysi turlar avtomatik hisoblanadi (qo'lda berilgani bundan mustasno)
AUTO_KINDS = [
    ActivityKind.BORROW,
    ActivityKind.RETURN_ONTIME,
    ActivityKind.OVERDUE,
    ActivityKind.QUIZ_PASSED,
    ActivityKind.QUIZ_PERFECT,
    ActivityKind.QUIZ_FAILED,
]


class ActivityRecord(models.Model):
    """Bitta faollik yozuvi: kim, nima uchun, necha ball."""

    reader = models.ForeignKey(
        "readers.Reader",
        verbose_name="Kitobxon",
        on_delete=models.CASCADE,
        related_name="activity_records",
    )
    kind = models.CharField("Turi", max_length=20, choices=ActivityKind.choices)
    points = models.IntegerField("Ball", default=0)
    happened_at = models.DateField("Sana", default=timezone.localdate)

    loan = models.ForeignKey(
        "loans.Loan",
        verbose_name="Operatsiya",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_records",
    )
    assignment = models.ForeignKey(
        "quizzes.Assignment",
        verbose_name="Test topshirig'i",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_records",
    )

    # Dublikat yaratmaslik uchun: "loan:12:ontime", "quiz:34:passed" ko'rinishida.
    # Qo'lda berilgan ballarda bo'sh qoladi.
    source_key = models.CharField(
        "Manba kaliti", max_length=80, blank=True, db_index=True
    )
    note = models.CharField("Izoh", max_length=255, blank=True)
    awarded_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        verbose_name="Kim qo'shdi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="awarded_activity",
    )
    created_at = models.DateTimeField("Yaratilgan", default=timezone.now)

    class Meta:
        db_table = "activity_records"
        verbose_name = "Faollik yozuvi"
        verbose_name_plural = "Ijtimoiy faollik"
        ordering = ["-happened_at", "-created_at"]
        indexes = [
            models.Index(fields=["kind"]),
            models.Index(fields=["happened_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_key"],
                condition=~models.Q(source_key=""),
                name="activity_source_key_unique",
            )
        ]

    def __str__(self):
        return f"{self.reader.full_name}: {self.get_kind_display()} ({self.points:+d})"

    @property
    def is_manual(self):
        return self.kind == ActivityKind.MANUAL


# ---------------------------------------------------------------------------
# Ball qiymatlari — Sozlamalar bo'limidan o'zgartiriladi
# ---------------------------------------------------------------------------
POINT_SETTINGS = {
    ActivityKind.BORROW: ("activity_points_borrow", 1),
    ActivityKind.RETURN_ONTIME: ("activity_points_return_ontime", 3),
    ActivityKind.OVERDUE: ("activity_points_overdue", -2),
    ActivityKind.QUIZ_PASSED: ("activity_points_quiz_passed", 10),
    ActivityKind.QUIZ_PERFECT: ("activity_points_quiz_perfect", 5),
    ActivityKind.QUIZ_FAILED: ("activity_points_quiz_failed", 0),
}


def points_for(kind):
    """Ball qiymatini sozlamalardan oladi."""
    from apps.core.models import SystemSetting

    key, default = POINT_SETTINGS.get(kind, (None, 0))
    if not key:
        return 0
    return SystemSetting.get_int(key, default)


def point_settings_defaults():
    """Sozlamalar bo'limida ko'rinadigan standart qiymatlar."""
    labels = {
        ActivityKind.BORROW: "Faollik bali: kitob olgani uchun",
        ActivityKind.RETURN_ONTIME: "Faollik bali: muddatida qaytargani uchun",
        ActivityKind.OVERDUE: "Faollik bali: kechiktirgani uchun (manfiy bo'lishi mumkin)",
        ActivityKind.QUIZ_PASSED: "Faollik bali: testdan o'tgani uchun",
        ActivityKind.QUIZ_PERFECT: "Faollik bali: testni 100% yechgani uchun (qo'shimcha)",
        ActivityKind.QUIZ_FAILED: "Faollik bali: testdan o'tolmagani uchun",
    }
    rows = []
    for kind, (key, default) in POINT_SETTINGS.items():
        rows.append((key, str(default), labels.get(kind, key)))
    return rows
