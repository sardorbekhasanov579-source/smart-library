"""Telegram bot mantig'i — polling va webhook rejimlari uchun umumiy.

`run_telegram_bot` komandasi (lokal ishlash uchun) va `webhooks.py` dagi
webhook view bir xil `handle_update()` funksiyasidan foydalanadi.

Imkoniyatlar:
  * bazadagi kitobxon raqamini yuborsa — hisobi ulanadi;
  * bazada yo'q bo'lsa — shu yerning o'zida ro'yxatdan o'tadi (F.I.Sh. va
    turi so'raladi) va darhol kabinet ochiladi;
  * «📱 Kabinet» — ilovaga bir bosishda kirish havolasi;
  * adminlar uchun: kitob olish so'rovlarini «Tasdiqlash / Rad etish».
"""
import logging
import re

from django.db import transaction
from django.utils import timezone

from apps.quizzes import telegram
from apps.quizzes.models import AssignmentStatus, TelegramAccount, TelegramRegistration
from apps.quizzes.services import find_reader_by_phone, link_telegram_account
from apps.quizzes.utils import normalize_phone, pretty_phone

logger = logging.getLogger(__name__)


def cabinet_link():
    """Kitobxon ilovasining (kabinet) to'liq manzili."""
    from django.urls import reverse

    from apps.core.models import SystemSetting

    base = (SystemSetting.get("site_base_url", "") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}{reverse('quizzes:portal')}"


def cabinet_keyboard(reader, chat_id):
    """«Kabinetni ochish» tugmasi — parolsiz, bir bosishda kiradi."""
    from apps.quizzes.selfservice import login_url

    return telegram.link_keyboard(login_url(reader, chat_id), "📱 Kabinetni ochish")


HELP_TEXT = (
    "ℹ️ <b>Yordam</b>\n\n"
    "/start — ro'yxatdan o'tish (telefon raqamni tasdiqlash)\n"
    "/kabinet — ilovani ochish\n"
    "/testlar — ochiq testlarim\n"
    "/kitoblarim — qo'limdagi kitoblar\n"
    "/id — chat ID (administrator uchun)\n\n"
    "Ilovada kitobni topib «Shu kitobni oldim» deb belgilang — kutubxonachi "
    "tasdiqlaydi. O'qib bo'lgach, o'sha kitob bo'yicha testni ilovaning o'zidan "
    "topshirasiz."
)

READER_TYPES = {
    "talaba": "student", "o'quvchi": "student", "student": "student",
    "o'qituvchi": "teacher", "oqituvchi": "teacher", "ustoz": "teacher",
    "xodim": "employee",
    "boshqa": "other",
}
TYPE_BUTTONS = [["🎓 Talaba", "👨‍🏫 O'qituvchi"], ["💼 Xodim", "👤 Boshqa"]]


def handle_update(update):
    """Telegramdan kelgan bitta yangilanishni qayta ishlaydi."""
    update = update or {}
    callback = update.get("callback_query")
    if callback:
        handle_callback(callback)
        return

    message = update.get("message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    if chat_id is None:
        return
    # Faqat shaxsiy chat: guruhdagi yozishmalarga javob bermaymiz
    if message.get("chat", {}).get("type", "private") != "private":
        if (message.get("text") or "").strip().lower().startswith("/id"):
            telegram.safe_send(chat_id, f"Chat ID: <code>{chat_id}</code>")
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
        return
    if low.startswith("/id"):
        telegram.safe_send(chat_id, f"Chat ID: <code>{chat_id}</code>")
        return

    # Ro'yxatdan o'tish davom etayotgan bo'lsa — matn o'shanga javob
    registration = TelegramRegistration.objects.filter(chat_id=chat_id).first()
    if registration and not low.startswith("/"):
        handle_registration_step(registration, text, user)
        return

    if low.startswith("/kabinet") or "kabinet" in low or "ilova" in low:
        handle_cabinet(chat_id)
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


def handle_callback(callback):
    data = callback.get("data") or ""
    if data.startswith("br:"):
        from apps.loans.requests import handle_callback as borrow_callback

        borrow_callback(callback)
        return
    telegram.answer_callback(callback.get("id"), "")


def _verified_account(chat_id):
    return (
        TelegramAccount.objects.filter(chat_id=chat_id, is_verified=True)
        .select_related("reader")
        .first()
    )


def handle_start(chat_id, user):
    account = _verified_account(chat_id)
    if account:
        account.last_seen = timezone.now()
        account.save(update_fields=["last_seen"])
        telegram.safe_send(
            chat_id,
            f"Assalomu alaykum, <b>{account.reader.full_name}</b>! 👋\n\n"
            "Hisobingiz ulangan. Ilovani ochish uchun pastdagi tugmani bosing.",
            reply_markup=telegram.main_menu_keyboard(),
        )
        handle_cabinet(chat_id)
        return

    TelegramRegistration.objects.filter(chat_id=chat_id).delete()
    name = (user or {}).get("first_name") or "kitobxon"
    telegram.safe_send(
        chat_id,
        f"Assalomu alaykum, {name}! 👋\n\n"
        "Men kutubxona botiman. Davom etish uchun telefon raqamingiz kerak — "
        "kutubxonada ro'yxatda bo'lsangiz hisobingiz ulanadi, bo'lmasa shu "
        "yerning o'zida 1 daqiqada ro'yxatdan o'tasiz.\n\n"
        "Pastdagi <b>«Raqamimni yuborish»</b> tugmasini bosing.",
        reply_markup=telegram.phone_request_keyboard(),
    )


def handle_contact(chat_id, contact, user):
    # Boshqa odamning kontaktini yuborib uning hisobiga ulanib olmasin
    owner = (contact or {}).get("user_id")
    if owner is not None and user.get("id") is not None and owner != user.get("id"):
        telegram.safe_send(
            chat_id,
            "Iltimos, o'zingizning raqamingizni pastdagi tugma orqali yuboring.",
            reply_markup=telegram.phone_request_keyboard(),
        )
        return

    phone = (contact or {}).get("phone_number", "")
    reader = find_reader_by_phone(phone)
    if not reader:
        start_registration(chat_id, phone, user)
        return

    TelegramRegistration.objects.filter(chat_id=chat_id).delete()
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
        f"🆔 {reader.reader_code}\n\n" + HELP_TEXT,
        reply_markup=telegram.main_menu_keyboard(),
    )
    handle_cabinet(chat_id)


# ---------------------------------------------------------------------------
# Bot orqali ro'yxatdan o'tish
# ---------------------------------------------------------------------------
def start_registration(chat_id, phone, user):
    TelegramRegistration.objects.update_or_create(
        chat_id=chat_id,
        defaults={
            "phone": normalize_phone(phone),
            "step": TelegramRegistration.STEP_NAME,
            "full_name": "",
            "username": (user or {}).get("username", "") or "",
            "first_name": (user or {}).get("first_name", "") or "",
        },
    )
    telegram.safe_send(
        chat_id,
        f"📱 {pretty_phone(phone)} raqami kutubxona bazasida yo'q — "
        "keling, hoziroq ro'yxatdan o'tamiz.\n\n"
        "✍️ <b>Familiya, ism va otangizning ismini</b> yozing.\n"
        "Masalan: <i>Hasanov Sardor Odil o'g'li</i>",
        reply_markup=telegram.remove_keyboard(),
    )


NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ'‘’ʻʼ`\- .]+$")


def clean_full_name(text):
    """F.I.Sh. ni tekshiradi va chiroyli ko'rinishga keltiradi. Xato bo'lsa ''."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not (5 <= len(text) <= 120) or not NAME_RE.match(text):
        return ""
    words = text.split(" ")
    if len(words) < 2 or any(len(w.strip("'‘’ʻʼ`-.")) < 2 for w in words[:2]):
        return ""

    def cap(word):
        lowered = word.lower()
        if lowered in ("o'g'li", "o‘g‘li", "qizi", "ogli"):
            return lowered
        return word[:1].upper() + word[1:].lower()

    return " ".join(cap(w) for w in words)


def handle_registration_step(registration, text, user):
    chat_id = registration.chat_id

    if registration.step == TelegramRegistration.STEP_NAME:
        name = clean_full_name(text)
        if not name:
            telegram.safe_send(
                chat_id,
                "Iltimos, familiya va ismingizni to'liq, harflar bilan yozing.\n"
                "Masalan: <i>Hasanov Sardor Odil o'g'li</i>",
            )
            return
        registration.full_name = name
        registration.step = TelegramRegistration.STEP_TYPE
        registration.save(update_fields=["full_name", "step", "updated_at"])
        telegram.safe_send(
            chat_id,
            f"Rahmat, <b>{name}</b>!\n\nSiz kimsiz? Pastdagi tugmalardan birini tanlang.",
            reply_markup=telegram.choice_keyboard(TYPE_BUTTONS),
        )
        return

    if registration.step == TelegramRegistration.STEP_TYPE:
        key = re.sub(r"[^\w' ]", "", text.lower().replace("‘", "'").replace("’", "'")).strip()
        reader_type = READER_TYPES.get(key)
        if reader_type is None:
            reader_type = next((v for k, v in READER_TYPES.items() if k in key), None)
        if reader_type is None:
            telegram.safe_send(
                chat_id, "Pastdagi tugmalardan birini tanlang.",
                reply_markup=telegram.choice_keyboard(TYPE_BUTTONS),
            )
            return
        finish_registration(registration, reader_type)


def finish_registration(registration, reader_type):
    from apps.readers.models import Reader

    chat_id = registration.chat_id
    with transaction.atomic():
        reader = find_reader_by_phone(registration.phone)
        created = reader is None
        if created:
            reader = Reader.objects.create(
                full_name=registration.full_name,
                reader_code=Reader.generate_code(),
                phone="+" + registration.phone if registration.phone.isdigit() else registration.phone,
                reader_type=reader_type,
                note=(
                    "Telegram bot orqali o'zi ro'yxatdan o'tgan "
                    f"({timezone.localdate():%d.%m.%Y})"
                ),
            )
        link_telegram_account(
            reader, chat_id,
            username=registration.username,
            first_name=registration.first_name,
            phone=registration.phone,
        )
        registration.delete()

    telegram.safe_send(
        chat_id,
        "🎉 <b>Ro'yxatdan o'tdingiz!</b>\n\n"
        f"👤 {reader.full_name}\n"
        f"🆔 Kitobxon kodi: <b>{reader.reader_code}</b>\n\n"
        "Endi ilovada kutubxona fondini ko'rishingiz, kitob qayerda turganini "
        "bilishingiz, olgan kitobingizni belgilab, test topshirishingiz mumkin.",
        reply_markup=telegram.main_menu_keyboard(),
    )
    handle_cabinet(chat_id)

    if created:
        from apps.core.models import AuditLog

        AuditLog.log(
            action=AuditLog.Action.CREATE, entity_type="reader", entity_id=reader.pk,
            details=f"Telegram bot orqali ro'yxatdan o'tdi: {reader.full_name}",
        )
        telegram.notify_admins(
            "🆕 <b>Yangi kitobxon (bot orqali)</b>\n\n"
            f"👤 {reader.full_name}\n"
            f"📞 {pretty_phone(reader.phone)}\n"
            f"🆔 {reader.reader_code} · {reader.get_reader_type_display()}"
        )


# ---------------------------------------------------------------------------
# Kabinet, testlar, kitoblar
# ---------------------------------------------------------------------------
def handle_cabinet(chat_id):
    from apps.quizzes.selfservice import login_url

    account = _verified_account(chat_id)
    if not account:
        handle_start(chat_id, {})
        return
    url = login_url(account.reader, chat_id)
    if not url:
        telegram.safe_send(chat_id, "Ilova manzili hali sozlanmagan. Kutubxonachiga ayting.")
        return
    markup = telegram.link_keyboard(url, "📱 Kabinetni ochish")
    text = (
        "📱 <b>Shaxsiy kabinet</b>\n\n"
        "Kitoblar bazasi, kitob qayerda turgani, olgan kitoblaringiz va testlar.\n"
        "Tugma 1 soat amal qiladi — keyin «📱 Kabinet» ni qayta bosing."
    )
    if not markup:
        text += f"\n\n👉 {url}"
    telegram.safe_send(chat_id, text, reply_markup=markup)


def handle_my_quizzes(chat_id):
    account = _verified_account(chat_id)
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
        telegram.safe_send(
            chat_id,
            "Hozir ochiq testingiz yo'q. ✅\n\n"
            "O'qigan kitobingiz bo'yicha testni ilovadagi «Testlar» bo'limidan "
            "o'zingiz boshlashingiz mumkin.",
            reply_markup=cabinet_keyboard(account.reader, chat_id),
        )
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
    account = _verified_account(chat_id)
    if not account:
        handle_start(chat_id, {})
        return

    loans = (
        account.reader.loans.select_related("copy__book__author")
        .filter(return_date__isnull=True)
        .order_by("due_date")
    )
    pending = account.reader.borrow_requests.filter(status="pending").select_related("book")
    if not loans and not pending:
        telegram.safe_send(
            chat_id, "Qo'lingizda kitob yo'q. 📚",
            reply_markup=cabinet_keyboard(account.reader, chat_id),
        )
        return

    lines = []
    if loans:
        lines.append("📚 <b>Qo'lingizdagi kitoblar</b>\n")
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
    if pending:
        lines.append("🕒 <b>Tasdiq kutilmoqda</b>")
        lines += [f"• {r.book.title}" for r in pending]
    telegram.safe_send(
        chat_id, "\n".join(lines),
        reply_markup=cabinet_keyboard(account.reader, chat_id),
    )
