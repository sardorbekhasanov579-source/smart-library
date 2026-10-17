"""Telegram webhook manzilini o'rnatadi yoki o'chiradi.

Serverga joylashtirilgandan keyin bir marta ishga tushiriladi:

    python manage.py set_telegram_webhook

Manzil `site_base_url` sozlamasidan olinadi (yoki --url bilan beriladi).
Manzil HTTPS bo'lishi shart — Telegram HTTP ni qabul qilmaydi.

Lokal kompyuterda ishlayotganda webhook kerak emas, o'rniga:
    python manage.py run_telegram_bot

Webhookni o'chirish (polling'ga qaytish):
    python manage.py set_telegram_webhook --delete
"""
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.core.models import SystemSetting
from apps.quizzes import telegram


class Command(BaseCommand):
    help = "Telegram webhook manzilini o'rnatadi (serverda ishlatish uchun)"

    def add_arguments(self, parser):
        parser.add_argument("--url", help="Saytning to'liq HTTPS manzili")
        parser.add_argument("--delete", action="store_true", help="Webhookni o'chirish")
        parser.add_argument("--info", action="store_true", help="Joriy holatni ko'rsatish")
        parser.add_argument(
            "--drop-pending", action="store_true",
            help="Kutib turgan eski xabarlarni tashlab yuborish",
        )

    def handle(self, *args, **options):
        if not telegram.is_configured():
            raise CommandError(
                "Telegram bot tokeni yo'q. Sozlamalarda `telegram_bot_token` ni to'ldiring."
            )

        if options["info"]:
            self.show_info()
            return

        if options["delete"]:
            telegram.delete_webhook()
            self.stdout.write(self.style.SUCCESS("Webhook o'chirildi."))
            self.stdout.write("Endi long-polling ishlatish mumkin: run_telegram_bot")
            return

        base = (options["url"] or SystemSetting.get("site_base_url", "") or "").strip()
        base = base.rstrip("/")
        if not base:
            raise CommandError(
                "Sayt manzili yo'q. --url bilan bering yoki Sozlamalarda "
                "`site_base_url` ni to'ldiring."
            )
        if not base.startswith("https://"):
            raise CommandError(
                f"Telegram faqat HTTPS manzilni qabul qiladi. Hozirgi manzil: {base}\n"
                "Lokal kompyuterda sinash uchun `run_telegram_bot` dan foydalaning."
            )

        secret = telegram.webhook_secret()
        path = reverse("quizzes:telegram_webhook", args=[secret])
        url = base + path

        try:
            telegram.set_webhook(url, secret=secret, drop_pending=options["drop_pending"])
        except telegram.TelegramError as exc:
            raise CommandError(f"Webhook o'rnatilmadi: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Webhook o'rnatildi."))
        self.stdout.write(f"Manzil: {url}")
        self.stdout.write("")
        self.show_info()

    def show_info(self):
        try:
            info = telegram.get_webhook_info() or {}
        except telegram.TelegramError as exc:
            self.stderr.write(f"Holatni olishda xato: {exc}")
            return
        self.stdout.write("Joriy holat:")
        self.stdout.write(f"  URL: {info.get('url') or '(o‘rnatilmagan)'}")
        self.stdout.write(f"  Kutayotgan xabarlar: {info.get('pending_update_count', 0)}")
        if info.get("last_error_message"):
            self.stdout.write(
                self.style.WARNING(f"  Oxirgi xato: {info['last_error_message']}")
            )
