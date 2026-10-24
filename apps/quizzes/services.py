"""Testlar va Telegram uchun biznes amallari (views va komandalar shu yerdan foydalanadi)."""
import logging

from django.db.models import Q
from django.utils import timezone

from apps.quizzes import telegram
from apps.quizzes.models import (
    Assignment,
    AssignmentStatus,
    OtpCode,
    Quiz,
    TelegramAccount,
)
from apps.quizzes.utils import normalize_phone, phone_variants, pretty_phone
from apps.readers.models import Reader, ReaderStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Kitobxonni telefon raqami bo'yicha topish
# ---------------------------------------------------------------------------
def find_reader_by_phone(phone):
    """Telefon raqam bo'yicha kitobxonni topadi (format farqiga chidamli)."""
    variants = phone_variants(phone)
    if not variants:
        return None
    query = Q()
    for value in variants:
        query |= Q(phone=value)
    reader = Reader.objects.filter(query).exclude(status=ReaderStatus.ARCHIVED).first()
    if reader:
        return reader
    # Bazada " ", "-", "(" kabi belgilar bo'lsa - qo'lda solishtiramiz
    target = normalize_phone(phone)
    for item in Reader.objects.exclude(phone="").only("id", "phone", "status"):
        if normalize_phone(item.phone) == target:
            return item
    return None


# ---------------------------------------------------------------------------
# Telegram hisobini ulash
# ---------------------------------------------------------------------------
def link_telegram_account(reader, chat_id, username="", first_name="", phone=""):
    """Kitobxon bilan Telegram chatini bog'laydi (bitta chat - bitta kitobxon)."""
    TelegramAccount.objects.filter(chat_id=chat_id).exclude(reader=reader).delete()
    account, _created = TelegramAccount.objects.update_or_create(
        reader=reader,
        defaults={
            "chat_id": chat_id,
            "username": username or "",
            "first_name": first_name or "",
            "phone": normalize_phone(phone) or normalize_phone(reader.phone),
            "is_verified": True,
            "last_seen": timezone.now(),
        },
    )
    return account


def reader_chat_id(reader):
    account = getattr(reader, "telegram", None)
    return account.chat_id if account and account.is_verified else None


def reader_notify_chat_id(reader):
    """Bildirishnoma uchun chat ID.

    Kitobxon ilovaning sozlamalaridan bildirishnomalarni o'chirib qo'ygan
    bo'lsa None qaytaradi. Kirish kodi bunga bog'liq emas — u har holda
    yuboriladi (`reader_chat_id`).
    """
    account = getattr(reader, "telegram", None)
    if not account or not account.is_verified:
        return None
    if not account.notifications_enabled:
        return None
    return account.chat_id


# ---------------------------------------------------------------------------
# OTP (bir martalik kod)
# ---------------------------------------------------------------------------
def send_login_code(phone):
    """Kitobxonga Telegram orqali kirish kodini yuboradi.

    (ok, xabar) qaytaradi.
    """
    reader = find_reader_by_phone(phone)
    if not reader:
        return False, "Bu raqam bo'yicha kitobxon topilmadi. Kutubxonachiga murojaat qiling."
    if reader.status == ReaderStatus.BLOCKED:
        return False, "Hisobingiz bloklangan. Kutubxonachiga murojaat qiling."

    chat_id = reader_chat_id(reader)
    if not chat_id:
        return False, (
            "Telegram hisobingiz ulanmagan. Botga /start yuborib, "
            "telefon raqamingizni tasdiqlang."
        )

    otp = OtpCode.issue(phone, reader=reader, chat_id=chat_id)
    text = (
        f"🔐 <b>Kirish kodi: {otp.code}</b>\n\n"
        f"Kod {OtpCode.CODE_TTL_MINUTES} daqiqa amal qiladi.\n"
        "Kodni boshqa hech kimga bermang."
    )
    ok, error = telegram.safe_send(chat_id, text)
    if not ok:
        return False, f"Kod yuborilmadi: {error}"
    return True, f"Kod {pretty_phone(phone)} raqamiga ulangan Telegramga yuborildi."


# ---------------------------------------------------------------------------
# Test to'plamini olish / yaratish
# ---------------------------------------------------------------------------
def get_or_create_quiz(book, user=None, force=False, question_count=None):
    """Kitob uchun tayyor testni qaytaradi, bo'lmasa AI orqali yaratadi.

    (quiz, yaratildimi, xabar) qaytaradi.
    """
    from apps.core.models import SystemSetting
    from apps.quizzes.ai import generate_questions

    if not force:
        quiz = (
            Quiz.objects.filter(book=book, is_active=True)
            .order_by("-created_at")
            .first()
        )
        if quiz and quiz.is_ready:
            return quiz, False, "Mavjud test ishlatildi."

    target = question_count or SystemSetting.quiz_question_count()
    questions, source, message = generate_questions(book, target)
    if not questions:
        return None, False, message or "Savollar yaratilmadi."

    quiz = Quiz.objects.create(
        book=book,
        source=source,
        question_target=target,
        pass_percent=SystemSetting.quiz_pass_percent(),
        created_by=user if getattr(user, "pk", None) else None,
        note=message[:255] if message else "",
    )
    save_questions(quiz, questions)
    return quiz, True, message or f"{quiz.questions_count} ta savol yaratildi."


def save_questions(quiz, questions):
    """questions: [{"text":..., "choices":[...], "correct_index":0, "explanation":...}]"""
    from apps.quizzes.models import Choice, Question

    created = 0
    for index, item in enumerate(questions, start=1):
        text = (item.get("text") or "").strip()
        choices = [str(c).strip() for c in (item.get("choices") or []) if str(c).strip()]
        if not text or len(choices) < 2:
            continue
        try:
            correct_index = int(item.get("correct_index", 0))
        except (TypeError, ValueError):
            correct_index = 0
        if not 0 <= correct_index < len(choices):
            correct_index = 0

        question = Question.objects.create(
            quiz=quiz,
            text=text,
            order=index,
            explanation=(item.get("explanation") or "").strip(),
        )
        Choice.objects.bulk_create(
            [
                Choice(
                    question=question,
                    text=value[:500],
                    is_correct=(position == correct_index),
                    order=position + 1,
                )
                for position, value in enumerate(choices)
            ]
        )
        created += 1
    return created


# ---------------------------------------------------------------------------
# Topshiriq yuborish
# ---------------------------------------------------------------------------
def send_assignment(assignment, base_url=None):
    """Kitobxonga test havolasini Telegram orqali yuboradi."""
    chat_id = reader_notify_chat_id(assignment.reader)
    link = assignment.absolute_link(base_url)
    if not chat_id:
        account = getattr(assignment.reader, "telegram", None)
        if account and account.is_verified and not account.notifications_enabled:
            note = "Kitobxon bildirishnomalarni o'chirgan"
            reason = (
                "Kitobxon ilovada bildirishnomalarni o'chirib qo'ygan. "
                "Test kabinetdagi «Testlarim» bo'limida ko'rinadi."
            )
        else:
            note = "Telegram ulanmagan"
            reason = "Kitobxonning Telegram hisobi ulanmagan."
        assignment.delivery_note = note
        assignment.save(update_fields=["delivery_note"])
        return False, reason

    book = assignment.book
    deadline = timezone.localtime(assignment.deadline) if assignment.deadline else None
    text = (
        f"📚 <b>{book.title}</b>\n"
        f"✍️ {book.author.full_name}\n\n"
        f"Assalomu alaykum, {assignment.reader.full_name}!\n"
        f"Kitobni qaytarish muddati yaqinlashdi"
        + (f" — <b>{deadline:%d.%m.%Y}</b>" if deadline else "")
        + ".\n\n"
        f"Kitobni o'qiganingizni tasdiqlash uchun <b>{assignment.question_count} ta savoldan</b> "
        f"iborat testni yechib chiqing.\n"
        f"O'tish chegarasi: <b>{assignment.pass_percent}%</b>\n\n"
        f"👉 {link}"
    )
    ok, error = telegram.safe_send(
        chat_id, text, reply_markup=telegram.link_keyboard(link)
    )
    if not ok:
        assignment.delivery_note = error[:255]
        assignment.save(update_fields=["delivery_note"])
        return False, error

    assignment.status = AssignmentStatus.SENT
    assignment.sent_at = timezone.now()
    assignment.delivery_note = "Telegram orqali yuborildi"
    assignment.save(update_fields=["status", "sent_at", "delivery_note"])
    return True, "Yuborildi."


def notify_admins_result(assignment, attempt=None):
    """Natijani adminlarga xabar qiladi."""
    reader = assignment.reader
    book = assignment.book
    percent = attempt.percent if attempt else assignment.best_percent

    if assignment.status == AssignmentStatus.PASSED:
        head = "✅ <b>Kitob o'qilgan</b>"
        verdict = f"natija <b>{percent}%</b> (chegara {assignment.pass_percent}%)"
    elif assignment.status == AssignmentStatus.EXPIRED:
        head = "⌛️ <b>Test ishlanmadi</b>"
        verdict = "muddat tugadi, kitobxon testni yechmadi"
    else:
        head = "❌ <b>Kitob o'qilmagan ko'rinadi</b>"
        verdict = f"natija <b>{percent}%</b> (chegara {assignment.pass_percent}%)"

    text = (
        f"{head}\n\n"
        f"👤 {reader.full_name} ({reader.reader_code})\n"
        f"📚 {book.title} — {book.author.full_name}\n"
        f"📊 {verdict}\n"
    )
    if attempt:
        text += f"✔️ To'g'ri javob: {attempt.correct_count}/{attempt.total_questions}\n"
    if assignment.loan_id:
        text += f"📅 Qaytarish muddati: {assignment.loan.due_date:%d.%m.%Y}\n"

    sent = telegram.notify_admins(text)
    if sent and not assignment.admin_notified:
        assignment.admin_notified = True
        assignment.save(update_fields=["admin_notified"])
    return sent


def expire_overdue_assignments(notify=True):
    """Muddati o'tgan, ishlanmagan topshiriqlarni yopadi va adminga xabar beradi."""
    now = timezone.now()
    stale = Assignment.objects.filter(
        deadline__lt=now,
        status__in=[
            AssignmentStatus.PENDING,
            AssignmentStatus.SENT,
            AssignmentStatus.STARTED,
        ],
    ).select_related("reader", "quiz__book__author", "loan")

    closed = 0
    for assignment in stale:
        assignment.status = AssignmentStatus.EXPIRED
        assignment.finished_at = now
        assignment.save(update_fields=["status", "finished_at"])
        closed += 1
        if notify:
            try:
                notify_admins_result(assignment)
            except Exception:  # pragma: no cover
                logger.exception("Adminga xabar yuborilmadi: %s", assignment.pk)
    return closed


def log_quiz_event(user, details, entity_id=None):
    from apps.core.models import AuditLog

    AuditLog.log(
        user=user,
        action=AuditLog.Action.UPDATE,
        entity_type="quiz",
        entity_id=entity_id,
        details=details,
    )
