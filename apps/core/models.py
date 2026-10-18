"""Tizim sozlamalari va audit jurnali (settings, audit_logs jadvallari)."""
from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone


class SystemSetting(models.Model):
    """ER: settings (id, key, value, description)."""

    key = models.CharField("Kalit", max_length=100, unique=True)
    value = models.CharField("Qiymat", max_length=255)
    description = models.CharField("Tavsif", max_length=255, blank=True)

    class Meta:
        db_table = "settings"
        verbose_name = "Sozlama"
        verbose_name_plural = "Tizim sozlamalari"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} = {self.value}"

    # -- Qulay kirish usullari ----------------------------------------------
    @classmethod
    def get(cls, key, default=None):
        obj = cls.objects.filter(key=key).first()
        return obj.value if obj else default

    @classmethod
    def get_int(cls, key, default=0):
        try:
            return int(cls.get(key, default))
        except (TypeError, ValueError):
            return default

    @classmethod
    def set(cls, key, value, description=""):
        obj, _ = cls.objects.update_or_create(
            key=key, defaults={"value": str(value), "description": description}
        )
        return obj

    @classmethod
    def loan_days(cls):
        return cls.get_int("loan_days", django_settings.DEFAULT_LOAN_DAYS)

    @classmethod
    def max_books_per_reader(cls):
        return cls.get_int(
            "max_books_per_reader", django_settings.DEFAULT_MAX_BOOKS_PER_READER
        )

    @classmethod
    def library_name(cls):
        return cls.get("library_name", "Smart Library")

    @classmethod
    def fine_per_day(cls):
        return cls.get_int("fine_per_day", 0)

    # -- Testlar moduli (apps.quizzes) --------------------------------------
    @classmethod
    def quiz_question_count(cls):
        return cls.get_int(
            "quiz_question_count",
            getattr(django_settings, "DEFAULT_QUIZ_QUESTION_COUNT", 30),
        )

    @classmethod
    def quiz_pass_percent(cls):
        return cls.get_int(
            "quiz_pass_percent",
            getattr(django_settings, "DEFAULT_QUIZ_PASS_PERCENT", 70),
        )

    @classmethod
    def quiz_days_before_due(cls):
        return cls.get_int(
            "quiz_days_before_due",
            getattr(django_settings, "DEFAULT_QUIZ_DAYS_BEFORE_DUE", 1),
        )

    @classmethod
    def defaults(cls):
        """Tizim birinchi ishga tushganda yaratiladigan sozlamalar."""
        return [
            ("library_name", "Smart Library", "Kutubxona nomi"),
            ("loan_days", "14", "Kitob berish muddati (kun)"),
            ("max_books_per_reader", "5", "Bir kitobxonga bir vaqtda beriladigan kitoblar soni"),
            ("fine_per_day", "0", "Kechikkan har bir kun uchun jarima (so'm)"),
            ("allow_reservations", "1", "Kitobxonlar buyurtma bera olsinmi (1/0)"),
            # --- Testlar va Telegram ---
            ("site_base_url", "http://127.0.0.1:8000",
             "Test havolalari uchun sayt manzili (Telegramga yuboriladi)"),
            ("quiz_question_count", "30", "Har bir test uchun savollar soni"),
            ("quiz_pass_percent", "70", "'Kitob o'qilgan' deb hisoblash chegarasi (%)"),
            ("quiz_days_before_due", "1", "Qaytarish muddatidan necha kun oldin test yuborilsin"),
            ("quiz_show_answers", "1", "Kitobxon natijadan keyin to'g'ri javoblarni ko'rsinmi (1/0)"),
            ("telegram_bot_token", "", "BotFather'dan olingan bot tokeni"),
            ("telegram_admin_chat_id", "",
             "Natijalar yuboriladigan admin chat ID lari (vergul bilan)"),
            ("telegram_bot_username", "",
             "Bot username (avtomatik aniqlanadi, masalan: smart_library_bot)"),
            ("ai_provider", "anthropic",
             "Savol generatori: anthropic, openai yoki gemini (gemini'da bepul tarif bor)"),
            ("ai_api_key", "", "AI provayderining API kaliti"),
            ("ai_model", "", "AI modeli nomi (bo'sh bo'lsa standart model)"),
        ]


class AuditLog(models.Model):
    """ER: audit_logs (id, user_id, action, entity_type, entity_id,
    created_at, details) - tizimdagi barcha muhim amallar tarixi."""

    class Action(models.TextChoices):
        CREATE = "create", "Qo'shildi"
        UPDATE = "update", "O'zgartirildi"
        DELETE = "delete", "O'chirildi"
        ISSUE = "issue", "Kitob berildi"
        RETURN = "return", "Kitob qaytarildi"
        LOGIN = "login", "Tizimga kirdi"
        LOGOUT = "logout", "Tizimdan chiqdi"

    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        verbose_name="Foydalanuvchi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField("Amal", max_length=16, choices=Action.choices)
    entity_type = models.CharField("Obyekt turi", max_length=50, blank=True)
    entity_id = models.PositiveIntegerField("Obyekt ID", null=True, blank=True)
    details = models.TextField("Tafsilotlar", blank=True)
    created_at = models.DateTimeField("Vaqti", default=timezone.now, db_index=True)

    class Meta:
        db_table = "audit_logs"
        verbose_name = "Jurnal yozuvi"
        verbose_name_plural = "Amallar jurnali"
        ordering = ["-created_at"]

    def __str__(self):
        who = self.user.full_name if self.user else "Tizim"
        return f"[{self.created_at:%d.%m.%Y %H:%M}] {who}: {self.get_action_display()}"

    @classmethod
    def log(cls, user=None, action=Action.UPDATE, entity_type="", entity_id=None, details=""):
        """Jurnalga yozuv qo'shadi. Xatolik yuzaga kelsa asosiy amalni to'xtatmaydi."""
        try:
            if user is not None and not getattr(user, "pk", None):
                user = None
            return cls.objects.create(
                user=user,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details[:2000],
            )
        except Exception:  # pragma: no cover - jurnal hech qachon jarayonni buzmasin
            return None

    @property
    def icon(self):
        return {
            self.Action.CREATE: "plus",
            self.Action.UPDATE: "edit",
            self.Action.DELETE: "trash",
            self.Action.ISSUE: "up",
            self.Action.RETURN: "down",
            self.Action.LOGIN: "in",
            self.Action.LOGOUT: "out",
        }.get(self.action, "dot")
