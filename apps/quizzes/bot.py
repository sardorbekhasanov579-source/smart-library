"""Telegram bot mantig'i — polling va webhook rejimlari uchun umumiy.

`run_telegram_bot` komandasi (lokal ishlash uchun) va `webhooks.py` dagi
webhook view bir xil `handle_update()` funksiyasidan foydalanadi.
"""
import logging

from django.utils import timezone

from apps.quizzes import telegram
from apps.quizzes.models import AssignmentStatus, TelegramAccount
from apps.quizzes.services import find_reader_by_phone, link_telegram_account
from apps.quizzes.utils import pretty_phone

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "ℹ️ <b>Yordam</b>\n\n"
    "/start — ro'yxatdan o'tish (telefon raqamni tasdiqlash)\n"
    "/testlar — ochiq testlarim\n"
    "/kitoblarim — qo'limdagi kitoblar\n"
    "/id — chat ID (administrator uchun)\n\n"
    "Kitobni qaytarish muddatiga 1 kun qolganda bot sizga "
    "o'sha kitob bo'yicha test yuboradi."
)


def handle_update(update):
    """Telegramdan kelgan bitta yangilanishni qayta ishlaydi."""
    message = (update or {}).get("message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    if chat_id is None:
        return

    contact = message.get("contact")
    text = (message.get("text") or "").strip()
    user = message.get("from", {}) or {}

    if contact:
        handle_contact(chat_id, contact, user)
        return

    low = text.lower()
    if low.startswith("/start"):
        handle_start(chat_id, user)
    elif low.startswith("/id"):
        telegram.safe_send(chat_id, f"Chat ID: <code>{chat_id}</code>")
    elif low.startswith("/yordam") or low.startswith("/help") or "yordam" in low:
        telegram.safe_send(chat_id, HELP_TEXT)
    elif low.startswith("/testlar") or "test" in low:
        handle_my_quizzes(chat_id)
    elif low.startswith("/kitoblarim") or "kitob" in low:
        handle_my_books(chat_id)
    else:
        telegram.safe_send(
            chat_id,
            "Tushunarsiz buyruq. /yordam ni yuboring.",
            reply_markup=telegram.main_menu_keyboard(),
        )


def handle_start(chat_id, user):
    account = (
        TelegramAccount.objects.filter(chat_id=chat_id).select_related("reader").first()
    )
    if account and account.is_verified:
        account.last_seen = timezone.now()
        account.save(update_fields=["last_seen"])
        telegram.safe_send(
            chat_id,
            f"Assalomu alaykum, <b>{account.reader.full_name}</b>! 👋\n\n"
            "Hisobingiz allaqachon ulangan.\n" + HELP_TEXT,
            reply_markup=telegram.main_menu_keyboard(),
        )
        return

    name = (user or {}).get("first_name") or "kitobxon"
    telegram.safe_send(
        chat_id,
        f"Assalomu alaykum, {name}! 👋\n\n"
        "Men kutubxona botiman. Sizni bazadagi kitobxon hisobingiz bilan "
        "bog'lash uchun telefon raqamingiz kerak.\n\n"
        "Pastdagi <b>«Raqamimni yuborish»</b> tugmasini bosing.",
        reply_markup=telegram.phone_request_keyboard(),
    )


def handle_contact(chat_id, contact, user):
    phone = (contact or {}).get("phone_number", "")
    reader = find_reader_by_phone(phone)
    if not reader:
        telegram.safe_send(
            chat_id,
            f"❌ {pretty_phone(phone)} raqami bazada topilmadi.\n\n"
            "Kutubxonachiga murojaat qilib, raqamingizni kitobxon kartasiga "
            "qo'shishni so'rang.",
            reply_markup=telegram.remove_keyboard(),
        )
        return

    link_telegram_account(
        reader,
        chat_id,
        username=(user or {}).get("username", ""),
        first_name=(user or {}).get("first_name", ""),
        phone=phone,
    )
    telegram.safe_send(
        chat_id,
        f"✅ Hisobingiz ulandi!\n\n"
        f"👤 <b>{reader.full_name}</b>\n"
        f"🆔 {reader.reader_code}\n\n"
        "Endi kitob qaytarish muddati yaqinlashganda sizga test keladi.\n\n"
        + HELP_TEXT,
        reply_markup=telegram.main_menu_keyboard(),
    )


def handle_my_quizzes(chat_id):
    account = (
        TelegramAccount.objects.filter(chat_id=chat_id).select_related("reader").first()
    )
    if not account:
        handle_start(chat_id, {})
        return

    open_items = (
        account.reader.quiz_assignments.select_related("quiz__book")
        .filter(
            status__in=[
                AssignmentStatus.SENT,
                AssignmentStatus.STARTED,
                AssignmentStatus.PENDING,
            ]
        )
        .order_by("deadline")
    )
    if not open_items:
        telegram.safe_send(chat_id, "Hozir ochiq testingiz yo'q. ✅")
        return

    lines = ["📝 <b>Ochiq testlar</b>\n"]
    for item in open_items[:10]:
        deadline = timezone.localtime(item.deadline) if item.deadline else None
        lines.append(
            f"📚 {item.quiz.book.title}\n"
            + (f"⏳ Muddat: {deadline:%d.%m.%Y %H:%M}\n" if deadline else "")
            + f"👉 {item.absolute_link()}\n"
        )
    telegram.safe_send(chat_id, "\n".join(lines))


def handle_my_books(chat_id):
    account = (
        TelegramAccount.objects.filter(chat_id=chat_id).select_related("reader").first()
    )
    if not account:
        handle_start(chat_id, {})
        return

    loans = (
        account.reader.loans.select_related("copy__book__author")
        .filter(return_date__isnull=True)
        .order_by("due_date")
    )
    if not loans:
        telegram.safe_send(chat_id, "Qo'lingizda kitob yo'q. 📚")
        return

    lines = ["📚 <b>Qo'lingizdagi kitoblar</b>\n"]
    for loan in loans:
        left = loan.days_left
        if left < 0:
            mark = f"⚠️ {abs(left)} kun kechikdi"
        elif left == 0:
            mark = "⏰ Bugun qaytarish kuni"
        else:
            mark = f"⏳ {left} kun qoldi"
        lines.append(
            f"• <b>{loan.copy.book.title}</b>\n"
            f"  {loan.copy.book.author.full_name}\n"
            f"  Muddat: {loan.due_date:%d.%m.%Y} — {mark}\n"
        )
    telegram.safe_send(chat_id, "\n".join(lines))
