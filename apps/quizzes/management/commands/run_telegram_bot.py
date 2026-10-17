"""Telegram botni long-polling rejimida ishga tushiradi (lokal ishlash uchun).

    python manage.py run_telegram_bot

Serverga joylashtirilganda webhook rejimi tavsiya etiladi — qarang:
    python manage.py set_telegram_webhook --help

Bot buyruqlari apps/quizzes/bot.py da tasvirlangan.
"""
import time

from django.core.management.base import BaseCommand, CommandError

from apps.quizzes import telegram
from apps.quizzes.bot import handle_update


class Command(BaseCommand):
    help = "Telegram botni long-polling rejimida ishga tushiradi"

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout", type=int, default=25,
            help="getUpdates uchun kutish vaqti (sekund)",
        )
        parser.add_argument(
            "--once", action="store_true",
            help="Faqat bir marta yangilanishlarni o'qib chiqadi (sinov uchun)",
        )

    def handle(self, *args, **options):
        if not telegram.is_configured():
            raise CommandError(
                "Telegram bot tokeni yo'q. Sozlamalar bo'limida `telegram_bot_token` ni "
                "to'ldiring yoki TELEGRAM_BOT_TOKEN muhit o'zgaruvchisini bering."
            )
        try:
            me = telegram.get_me()
        except telegram.TelegramError as exc:
            raise CommandError(f"Bot tokeni ishlamadi: {exc}") from exc

        # Polling va webhook bir vaqtda ishlay olmaydi
        telegram.delete_webhook()
        self.stdout.write(self.style.SUCCESS(f"Bot ishga tushdi: @{me.get('username')}"))
        self.stdout.write("To'xtatish uchun Ctrl+C\n")

        offset = None
        while True:
            try:
                updates = telegram.get_updates(
                    offset=offset, timeout=options["timeout"],
                    allowed_updates=["message"],
                )
            except telegram.TelegramError as exc:
                self.stderr.write(f"getUpdates xatosi: {exc}")
                time.sleep(5)
                continue
            except KeyboardInterrupt:
                self.stdout.write("\nTo'xtatildi.")
                return

            for update in updates:
                offset = update["update_id"] + 1
                try:
                    handle_update(update)
                except Exception as exc:  # pragma: no cover
                    self.stderr.write(f"Xabarni qayta ishlashda xato: {exc}")

            if options["once"]:
                self.stdout.write(f"{len(updates)} ta yangilanish o'qildi.")
                return
