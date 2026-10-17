"""Tashqi xizmatlar murojaat qiladigan manzillar.

1. Telegram webhook — bot serverga joylashtirilganda long-polling o'rniga
   ishlatiladi (doimiy ishlab turadigan alohida jarayon kerak bo'lmaydi).
2. Cron manzili — kunlik vazifani tashqi rejalashtiruvchi (masalan
   cron-job.org) orqali ishga tushirish uchun.

Ikkalasi ham maxfiy kalit bilan himoyalangan.
"""
import json
import logging
import threading

from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.quizzes import telegram
from apps.quizzes.bot import handle_update

logger = logging.getLogger(__name__)


def cron_secret():
    """Cron manzilidagi maxfiy kalit (bo'lmasa avtomatik yaratiladi)."""
    import secrets as _secrets

    from apps.core.models import SystemSetting

    value = (SystemSetting.get("cron_secret", "") or "").strip()
    if not value:
        value = _secrets.token_urlsafe(24)
        SystemSetting.set("cron_secret", value, "Kunlik vazifa manzilidagi maxfiy kalit")
    return value


@method_decorator(csrf_exempt, name="dispatch")
class TelegramWebhookView(View):
    """Telegram yuboradigan yangilanishlarni qabul qiladi.

    Manzil: /testlar/telegram/webhook/<secret>/
    Telegram qo'shimcha ravishda X-Telegram-Bot-Api-Secret-Token sarlavhasini
    yuboradi — u ham tekshiriladi.
    """

    def post(self, request, secret):
        expected = telegram.webhook_secret()
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != expected or (header and header != expected):
            logger.warning("Webhook: noto'g'ri kalit bilan murojaat")
            return HttpResponseForbidden("forbidden")

        try:
            update = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return HttpResponse("ok")  # Telegram qayta yubormasin

        try:
            handle_update(update)
        except Exception:  # pragma: no cover
            logger.exception("Webhook yangilanishini qayta ishlashda xato")
        # Telegram har doim 200 kutadi, aks holda xabarni qayta yuboraveradi
        return HttpResponse("ok")

    def get(self, request, secret):
        if secret != telegram.webhook_secret():
            return HttpResponseForbidden("forbidden")
        return HttpResponse("Telegram webhook ishlayapti.")


@method_decorator(csrf_exempt, name="dispatch")
class CronRunView(View):
    """Kunlik vazifani ishga tushiradi.

    Manzil: /testlar/cron/<secret>/
    Vazifa fonda bajariladi — so'rov darhol javob qaytaradi, chunki AI orqali
    savol yaratish uzoq davom etishi mumkin.
    """

    def get(self, request, secret):
        return self.run(request, secret)

    def post(self, request, secret):
        return self.run(request, secret)

    def run(self, request, secret):
        if secret != cron_secret():
            return HttpResponseForbidden("forbidden")

        def task():
            from django.core.management import call_command

            try:
                call_command("send_due_quizzes", verbosity=1)
            except Exception:  # pragma: no cover
                logger.exception("Kunlik vazifa xatosi")

        threading.Thread(target=task, daemon=True).start()
        return JsonResponse({"ok": True, "started": "send_due_quizzes"})
