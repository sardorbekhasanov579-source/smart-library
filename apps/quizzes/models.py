"""Testlar moduli: kitob bo'yicha savollar, kitobxonga biriktirilgan testlar,
urinishlar hamda Telegram hisoblari va bir martalik kodlar.

ER jadvallar:
  quizzes            - kitob uchun test to'plami
  quiz_questions     - savollar
  quiz_choices       - javob variantlari
  quiz_assignments   - kitobxonga biriktirilgan test (bitta loan uchun)
  quiz_attempts      - test ishlash urinishi
  quiz_answers       - urinishdagi har bir javob
  telegram_accounts  - kitobxonning Telegram chat_id si
  otp_codes          - bir martalik tasdiqlash kodlari
"""
import random
import secrets
from datetime import datetime, time, timedelta

from django.conf import settings as django_settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone


# ---------------------------------------------------------------------------
# Test to'plami
# ---------------------------------------------------------------------------
class QuizSource(models.TextChoices):
    AI = "ai", "AI yaratgan"
    FALLBACK = "fallback", "Avtomatik (ma'lumotlar asosida)"
    MANUAL = "manual", "Qo'lda kiritilgan"


class Quiz(models.Model):
    """Bitta kitob uchun savollar to'plami."""

    book = models.ForeignKey(
        "books.Book",
        verbose_name="Kitob",
        on_delete=models.CASCADE,
        related_name="quizzes",
    )
    title = models.CharField("Test nomi", max_length=255, blank=True)
    source = models.CharField(
        "Manba", max_length=16, choices=QuizSource.choices, default=QuizSource.AI
    )
    question_target = models.PositiveIntegerField("Savollar soni (maqsad)", default=30)
    pass_percent = models.PositiveIntegerField("O'tish chegarasi (%)", default=70)
    is_active = models.BooleanField("Faol", default=True)
    note = models.CharField("Izoh", max_length=255, blank=True)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        verbose_name="Yaratgan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_quizzes",
    )
    created_at = models.DateTimeField("Yaratilgan", default=timezone.now)

    class Meta:
        db_table = "quizzes"
        verbose_name = "Test"
        verbose_name_plural = "Testlar"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"{self.book.title} testi"

    def save(self, *args, **kwargs):
        if not self.title and self.book_id:
            self.title = f"{self.book.title} - bilim testi"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("quizzes:quiz_detail", args=[self.pk])

    @property
    def questions_count(self):
        return self.questions.count()

    @property
    def is_ready(self):
        """Test yuborishga tayyormi (kamida 5 ta savol bo'lsa)."""
        return self.is_active and self.questions_count >= 5

    def pick_question_ids(self, count=None):
        """Tasodifiy savollar to'plamini tanlaydi."""
        count = count or self.question_target or 30
        ids = list(self.questions.values_list("id", flat=True))
        random.shuffle(ids)
        return ids[:count]


class Question(models.Model):
    quiz = models.ForeignKey(
        Quiz, verbose_name="Test", on_delete=models.CASCADE, related_name="questions"
    )
    text = models.TextField("Savol")
    order = models.PositiveIntegerField("Tartib", default=0)
    explanation = models.TextField("Izoh / to'g'ri javob sharhi", blank=True)
    created_at = models.DateTimeField("Yaratilgan", default=timezone.now)

    class Meta:
        db_table = "quiz_questions"
        verbose_name = "Savol"
        verbose_name_plural = "Savollar"
        ordering = ["order", "id"]

    def __str__(self):
        return self.text[:80]

    @property
    def correct_choice(self):
        return self.choices.filter(is_correct=True).first()

    def shuffled_choices(self):
        items = list(self.choices.all())
        random.shuffle(items)
        return items


class Choice(models.Model):
    question = models.ForeignKey(
        Question, verbose_name="Savol", on_delete=models.CASCADE, related_name="choices"
    )
    text = models.CharField("Variant", max_length=500)
    is_correct = models.BooleanField("To'g'ri javob", default=False)
    order = models.PositiveIntegerField("Tartib", default=0)

    class Meta:
        db_table = "quiz_choices"
        verbose_name = "Javob varianti"
        verbose_name_plural = "Javob variantlari"
        ordering = ["order", "id"]

    def __str__(self):
        return self.text[:60]


# ---------------------------------------------------------------------------
# Kitobxonga biriktirilgan test
# ---------------------------------------------------------------------------
class AssignmentStatus(models.TextChoices):
    PENDING = "pending", "Yuborilmagan"
    SENT = "sent", "Yuborilgan"
    STARTED = "started", "Boshlangan"
    PASSED = "passed", "O'qigan (o'tdi)"
    FAILED = "failed", "O'qimagan (o'tmadi)"
    EXPIRED = "expired", "Muddati o'tdi"


class Assignment(models.Model):
    """Kitobxonga bitta kitob bo'yicha berilgan test topshirig'i."""

    quiz = models.ForeignKey(
        Quiz, verbose_name="Test", on_delete=models.PROTECT, related_name="assignments"
    )
    reader = models.ForeignKey(
        "readers.Reader",
        verbose_name="Kitobxon",
        on_delete=models.CASCADE,
        related_name="quiz_assignments",
    )
    loan = models.ForeignKey(
        "loans.Loan",
        verbose_name="Operatsiya",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quiz_assignments",
    )
    token = models.CharField("Maxfiy havola kodi", max_length=64, unique=True, db_index=True)
    status = models.CharField(
        "Holat", max_length=16, choices=AssignmentStatus.choices,
        default=AssignmentStatus.PENDING,
    )
    question_count = models.PositiveIntegerField("Savollar soni", default=30)
    pass_percent = models.PositiveIntegerField("O'tish chegarasi (%)", default=70)
    max_attempts = models.PositiveIntegerField("Ruxsat etilgan urinish", default=1)
    best_percent = models.PositiveIntegerField("Eng yaxshi natija (%)", default=0)
    deadline = models.DateTimeField("Topshirish muddati", null=True, blank=True)
    created_at = models.DateTimeField("Yaratilgan", default=timezone.now)
    sent_at = models.DateTimeField("Yuborilgan", null=True, blank=True)
    finished_at = models.DateTimeField("Yakunlangan", null=True, blank=True)
    admin_notified = models.BooleanField("Adminga xabar berildi", default=False)
    delivery_note = models.CharField("Yuborish izohi", max_length=255, blank=True)

    class Meta:
        db_table = "quiz_assignments"
        verbose_name = "Test topshirig'i"
        verbose_name_plural = "Test topshiriqlari"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["deadline"]),
        ]

    def __str__(self):
        return f"{self.reader.full_name} - {self.quiz.book.title}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    # -- havolalar ----------------------------------------------------------
    def get_absolute_url(self):
        return reverse("quizzes:take", args=[self.token])

    def absolute_link(self, base_url=None):
        """Telegramga yuborish uchun to'liq havola."""
        from apps.core.models import SystemSetting

        base = (base_url or SystemSetting.get("site_base_url", "") or "").rstrip("/")
        if not base:
            base = "http://127.0.0.1:8000"
        return base + self.get_absolute_url()

    # -- holat yordamchilari ------------------------------------------------
    @property
    def book(self):
        return self.quiz.book

    @property
    def is_finished(self):
        return self.status in {
            AssignmentStatus.PASSED,
            AssignmentStatus.FAILED,
            AssignmentStatus.EXPIRED,
        }

    @property
    def is_expired(self):
        return bool(self.deadline and timezone.now() > self.deadline)

    @property
    def attempts_used(self):
        return self.attempts.count()

    @property
    def can_attempt(self):
        if self.is_finished or self.is_expired:
            return False
        return self.attempts.filter(finished_at__isnull=False).count() < self.max_attempts

    @property
    def days_left(self):
        if not self.deadline:
            return None
        return (self.deadline.date() - timezone.localdate()).days

    # -- yaratish -----------------------------------------------------------
    @classmethod
    def deadline_for_loan(cls, loan):
        """Muddat: kitobni qaytarish kunining oxiri."""
        day = loan.due_date if loan else timezone.localdate() + timedelta(days=1)
        naive = datetime.combine(day, time(23, 59, 0))
        if timezone.is_naive(naive):
            return timezone.make_aware(naive, timezone.get_current_timezone())
        return naive

    @classmethod
    def create_for_loan(cls, loan, quiz, question_count=None, pass_percent=None):
        from apps.core.models import SystemSetting

        count = question_count or SystemSetting.quiz_question_count()
        percent = pass_percent or quiz.pass_percent or SystemSetting.quiz_pass_percent()
        return cls.objects.create(
            quiz=quiz,
            reader=loan.reader,
            loan=loan,
            question_count=min(count, max(quiz.questions_count, 1)),
            pass_percent=percent,
            deadline=cls.deadline_for_loan(loan),
        )

    # -- baholash -----------------------------------------------------------
    @transaction.atomic
    def apply_result(self, attempt):
        """Urinish yakunlanganda topshiriq holatini yangilaydi."""
        self.best_percent = max(self.best_percent, attempt.percent)
        if attempt.passed:
            self.status = AssignmentStatus.PASSED
            self.finished_at = timezone.now()
        elif self.attempts.filter(finished_at__isnull=False).count() >= self.max_attempts:
            self.status = AssignmentStatus.FAILED
            self.finished_at = timezone.now()
        else:
            self.status = AssignmentStatus.STARTED
        self.save(update_fields=["best_percent", "status", "finished_at"])
        return self


class Attempt(models.Model):
    """Bitta test ishlash urinishi."""

    assignment = models.ForeignKey(
        Assignment, verbose_name="Topshiriq", on_delete=models.CASCADE,
        related_name="attempts",
    )
    question_ids = models.JSONField("Berilgan savollar", default=list, blank=True)
    total_questions = models.PositiveIntegerField("Savollar soni", default=0)
    correct_count = models.PositiveIntegerField("To'g'ri javoblar", default=0)
    percent = models.PositiveIntegerField("Natija (%)", default=0)
    passed = models.BooleanField("O'tdi", default=False)
    started_at = models.DateTimeField("Boshlangan", default=timezone.now)
    finished_at = models.DateTimeField("Yakunlangan", null=True, blank=True)

    class Meta:
        db_table = "quiz_attempts"
        verbose_name = "Test urinishi"
        verbose_name_plural = "Test urinishlari"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.assignment.reader.full_name} - {self.percent}%"

    @property
    def is_open(self):
        return self.finished_at is None

    def questions(self):
        """Saqlangan tartibda savollarni qaytaradi."""
        ids = list(self.question_ids or [])
        if not ids:
            return []
        items = {q.id: q for q in Question.objects.filter(id__in=ids).prefetch_related("choices")}
        return [items[i] for i in ids if i in items]

    @transaction.atomic
    def grade(self, posted):
        """posted: {question_id: choice_id} ko'rinishidagi javoblar."""
        questions = self.questions()
        self.answers.all().delete()
        correct = 0
        rows = []
        for question in questions:
            choice_id = posted.get(question.id)
            choice = None
            if choice_id:
                choice = next((c for c in question.choices.all() if c.id == choice_id), None)
            is_correct = bool(choice and choice.is_correct)
            if is_correct:
                correct += 1
            rows.append(
                Answer(attempt=self, question=question, choice=choice, is_correct=is_correct)
            )
        Answer.objects.bulk_create(rows)

        self.total_questions = len(questions)
        self.correct_count = correct
        self.percent = round(correct * 100 / len(questions)) if questions else 0
        self.passed = self.percent >= self.assignment.pass_percent
        self.finished_at = timezone.now()
        self.save(
            update_fields=[
                "total_questions", "correct_count", "percent", "passed", "finished_at",
            ]
        )
        self.assignment.apply_result(self)
        return self


class Answer(models.Model):
    attempt = models.ForeignKey(
        Attempt, verbose_name="Urinish", on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(
        Question, verbose_name="Savol", on_delete=models.CASCADE, related_name="answers"
    )
    choice = models.ForeignKey(
        Choice, verbose_name="Tanlangan variant", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="answers",
    )
    is_correct = models.BooleanField("To'g'ri", default=False)

    class Meta:
        db_table = "quiz_answers"
        verbose_name = "Javob"
        verbose_name_plural = "Javoblar"
        unique_together = [("attempt", "question")]

    def __str__(self):
        return f"{self.question_id} -> {self.choice_id}"


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
class TelegramAccount(models.Model):
    """Kitobxonning Telegram hisobi (xabar yuborish uchun chat_id)."""

    reader = models.OneToOneField(
        "readers.Reader",
        verbose_name="Kitobxon",
        on_delete=models.CASCADE,
        related_name="telegram",
    )
    chat_id = models.BigIntegerField("Telegram chat ID", unique=True)
    username = models.CharField("Telegram username", max_length=64, blank=True)
    first_name = models.CharField("Ism", max_length=100, blank=True)
    phone = models.CharField("Telefon", max_length=32, blank=True)
    is_verified = models.BooleanField("Tasdiqlangan", default=False)
    created_at = models.DateTimeField("Ulangan", default=timezone.now)
    last_seen = models.DateTimeField("Oxirgi aloqa", null=True, blank=True)

    class Meta:
        db_table = "telegram_accounts"
        verbose_name = "Telegram hisob"
        verbose_name_plural = "Telegram hisoblar"

    def __str__(self):
        return f"{self.reader.full_name} (@{self.username or self.chat_id})"


class OtpCode(models.Model):
    """Telefon raqam bo'yicha bir martalik kod (Telegram orqali yuboriladi)."""

    CODE_TTL_MINUTES = 5
    MAX_TRIES = 5

    phone = models.CharField("Telefon", max_length=32, db_index=True)
    code = models.CharField("Kod", max_length=8)
    reader = models.ForeignKey(
        "readers.Reader",
        verbose_name="Kitobxon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="otp_codes",
    )
    chat_id = models.BigIntegerField("Yuborilgan chat", null=True, blank=True)
    purpose = models.CharField("Maqsad", max_length=32, default="login")
    is_used = models.BooleanField("Ishlatilgan", default=False)
    tries = models.PositiveIntegerField("Urinishlar", default=0)
    created_at = models.DateTimeField("Yaratilgan", default=timezone.now)
    expires_at = models.DateTimeField("Amal qilish muddati")

    class Meta:
        db_table = "otp_codes"
        verbose_name = "Tasdiqlash kodi"
        verbose_name_plural = "Tasdiqlash kodlari"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phone} - {self.code}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def issue(cls, phone, reader=None, chat_id=None, purpose="login"):
        """Yangi kod yaratadi, oldingi ishlatilmaganlarini bekor qiladi."""
        from apps.quizzes.utils import normalize_phone

        phone = normalize_phone(phone)
        cls.objects.filter(phone=phone, purpose=purpose, is_used=False).update(is_used=True)
        return cls.objects.create(
            phone=phone,
            code=f"{secrets.randbelow(900000) + 100000}",
            reader=reader,
            chat_id=chat_id,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=cls.CODE_TTL_MINUTES),
        )

    @classmethod
    def check_code(cls, phone, code, purpose="login"):
        """(ok, xabar, obyekt) qaytaradi."""
        from apps.quizzes.utils import normalize_phone

        phone = normalize_phone(phone)
        otp = (
            cls.objects.filter(phone=phone, purpose=purpose, is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not otp:
            return False, "Kod topilmadi. Qaytadan kod so'rang.", None
        if otp.is_expired:
            return False, "Kodning amal qilish muddati tugagan.", otp
        if otp.tries >= cls.MAX_TRIES:
            return False, "Juda ko'p urinish. Yangi kod so'rang.", otp
        if str(code).strip() != otp.code:
            otp.tries += 1
            otp.save(update_fields=["tries"])
            return False, "Kod xato.", otp
        otp.is_used = True
        otp.save(update_fields=["is_used"])
        return True, "", otp
