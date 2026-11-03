"""Kitob olish so'rovlari: kitobxon belgilaydi -> admin tasdiqlaydi.

Tasdiqlash ikki joydan bo'ladi va natija bir xil:
  * Telegram — adminlarga kelgan xabardagi «Tasdiqlash / Rad etish» tugmalari;
  * Admin panel — «Kitob so'rovlari» sahifasi.
Qaysi biridan bosilsa ham, boshqa adminlardagi Telegram xabarlari yangilanadi
va kitobxonga natija yuboriladi.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.books.models import BookCopy, CopyStatus
from apps.loans.models import BorrowRequest, Loan

logger = logging.getLogger(__name__)

Status = BorrowRequest.Status


# ---------------------------------------------------------------------------
# Kitobxon tomoni
# ---------------------------------------------------------------------------
def pending_for(reader):
    return reader.borrow_requests.filter(status=Status.PENDING)


def create_request(reader, book, copy=None):
    """(ok, xabar, so'rov) qaytaradi."""
    from apps.readers.models import ReaderStatus

    if reader.status != ReaderStatus.ACTIVE:
        return False, "Hisobingiz faol emas. Kutubxonachiga murojaat qiling.", None
    if reader.overdue_loans_count:
        return False, (
            "Muddati o'tgan kitobingiz bor. Avval uni qaytaring, keyin yangi kitob olasiz."
        ), None
    if pending_for(reader).filter(book=book).exists():
        return False, "Bu kitob bo'yicha so'rovingiz allaqachon yuborilgan.", None
    if reader.active_loans.filter(copy__book=book).exists():
        return False, "Bu kitob allaqachon sizda turibdi.", None

    busy = reader.active_loans_count + pending_for(reader).count()
    if busy >= reader.book_limit:
        return False, (
            f"Bir vaqtda {reader.book_limit} ta kitob olish mumkin. Qo'lingizdagi "
            "kitoblardan birini qaytaring."
        ), None

    if copy is not None and (copy.book_id != book.pk or copy.status != CopyStatus.AVAILABLE):
        copy = None
    if copy is None and not book.copies.filter(status=CopyStatus.AVAILABLE).exists():
        return False, "Bu kitobning bo'sh nusxasi qolmagan.", None

    request = BorrowRequest.objects.create(reader=reader, book=book, copy=copy)
    try:
        notify_admins_new(request)
    except Exception:  # pragma: no cover - Telegram ishlamasa ham so'rov saqlanadi
        logger.exception("So'rov haqida adminga xabar yuborilmadi: %s", request.pk)
    return True, (
        "So'rov yuborildi. Kutubxonachi tasdiqlagach kitob «Mening sahifam»da "
        "paydo bo'ladi va Telegramga xabar keladi."
    ), request


def cancel_request(request, reader):
    if request.reader_id != reader.pk or not request.is_pending:
        return False
    request.status = Status.CANCELLED
    request.decided_at = timezone.now()
    request.decided_via = "kitobxon"
    request.save(update_fields=["status", "decided_at", "decided_via"])
    refresh_admin_messages(request)
    return True


# ---------------------------------------------------------------------------
# Admin tomoni
# ---------------------------------------------------------------------------
def _pick_copy(request, copy=None):
    """Beriladigan nusxa: admin tanlagani -> kitobxon tanlagani -> birinchi bo'sh."""
    for candidate in (copy, request.copy):
        if candidate is not None and candidate.book_id == request.book_id:
            fresh = BookCopy.objects.filter(pk=candidate.pk, status=CopyStatus.AVAILABLE).first()
            if fresh:
                return fresh
    return (
        request.book.copies.filter(status=CopyStatus.AVAILABLE)
        .order_by("inventory_number")
        .first()
    )


def approve(request, user=None, via="panel", by_name="", copy=None):
    """So'rovni tasdiqlaydi va kitobni beradi. (ok, xabar) qaytaradi."""
    with transaction.atomic():
        request = (
            BorrowRequest.objects.select_for_update()
            .select_related("reader", "book")
            .get(pk=request.pk)
        )
        if not request.is_pending:
            return False, f"Bu so'rov allaqachon ko'rib chiqilgan: {request.get_status_display()}."

        chosen = _pick_copy(request, copy)
        if chosen is None:
            return False, "Bu kitobning bo'sh nusxasi yo'q — avval nusxa holatini tekshiring."

        try:
            loan = Loan.issue(
                request.reader,
                chosen,
                user=user,
                note="Kitobxon ilovadagi so'rovi asosida"
                + (" (Telegram orqali tasdiqlandi)" if via == "telegram" else ""),
            )
        except ValueError as exc:
            return False, str(exc)

        request.status = Status.APPROVED
        request.copy = chosen
        request.loan = loan
        request.decided_at = timezone.now()
        request.decided_by = user if getattr(user, "pk", None) else None
        request.decided_via = via
        request.decided_by_name = by_name[:100]
        request.save()

    _after_decision(request)
    try:
        from apps.quizzes.selfservice import prepare_quiz_async

        prepare_quiz_async(request.book_id)  # test kitobxon ochguncha tayyor tursin
    except Exception:  # pragma: no cover
        logger.exception("Testni oldindan tayyorlab bo'lmadi")
    return True, (
        f"Tasdiqlandi: {request.reader.full_name} — «{request.book.title}» "
        f"(inv. {chosen.inventory_number}), muddat {loan.due_date:%d.%m.%Y}."
    )


def reject(request, user=None, via="panel", by_name="", reason=""):
    with transaction.atomic():
        request = BorrowRequest.objects.select_for_update().get(pk=request.pk)
        if not request.is_pending:
            return False, f"Bu so'rov allaqachon ko'rib chiqilgan: {request.get_status_display()}."
        request.status = Status.REJECTED
        request.reject_reason = (reason or "")[:255]
        request.decided_at = timezone.now()
        request.decided_by = user if getattr(user, "pk", None) else None
        request.decided_via = via
        request.decided_by_name = by_name[:100]
        request.save()
    _after_decision(request)
    return True, f"Rad etildi: {request.reader.full_name} — «{request.book.title}»."


def _after_decision(request):
    try:
        refresh_admin_messages(request)
        notify_reader(request)
    except Exception:  # pragma: no cover
        logger.exception("So'rov natijasi haqida xabar yuborilmadi: %s", request.pk)


# ---------------------------------------------------------------------------
# Telegram xabarlari
# ---------------------------------------------------------------------------
def admin_text(request):
    from apps.quizzes.utils import pretty_phone

    reader = request.reader
    book = request.book
    lines = [
        "📥 <b>Kitob olish so'rovi</b>",
        "",
        f"👤 {reader.full_name} ({reader.reader_code})",
    ]
    if reader.phone:
        lines.append(f"📞 {pretty_phone(reader.phone)}")
    lines.append(f"📚 <b>{book.title}</b> — {book.author.full_name}")
    if book.shelf_location:
        lines.append(f"📍 {book.shelf_location}")
    if request.copy_id:
        lines.append(f"🔖 Inv. {request.copy.inventory_number}")
    lines.append(
        f"🕒 {timezone.localtime(request.created_at):%d.%m.%Y %H:%M} · "
        f"qo'lida {reader.active_loans_count}/{reader.book_limit} kitob"
    )

    if request.status == Status.APPROVED:
        due = f", muddat {request.loan.due_date:%d.%m.%Y}" if request.loan_id else ""
        inv = f" (inv. {request.copy.inventory_number})" if request.copy_id else ""
        lines += ["", f"✅ <b>Tasdiqlandi</b>{inv}{due}", _decider_line(request)]
    elif request.status == Status.REJECTED:
        lines += ["", "❌ <b>Rad etildi</b>", _decider_line(request)]
        if request.reject_reason:
            lines.append(f"Sabab: {request.reject_reason}")
    elif request.status == Status.CANCELLED:
        lines += ["", "↩️ Kitobxon so'rovni bekor qildi"]
    return "\n".join(line for line in lines if line is not None)


def _decider_line(request):
    who = request.decider_label
    where = {"telegram": "Telegram", "panel": "admin panel"}.get(request.decided_via, "")
    parts = [p for p in (who, where) if p]
    return "— " + ", ".join(parts) if parts else ""


def admin_keyboard(request):
    return {
        "inline_keyboard": [[
            {"text": "✅ Tasdiqlash", "callback_data": f"br:a:{request.pk}"},
            {"text": "❌ Rad etish", "callback_data": f"br:r:{request.pk}"},
        ]]
    }


def notify_admins_new(request):
    from apps.quizzes import telegram

    if not telegram.is_configured():
        return
    sent = telegram.notify_admins_collect(admin_text(request), reply_markup=admin_keyboard(request))
    if sent:
        request.admin_messages = sent
        request.save(update_fields=["admin_messages"])


def refresh_admin_messages(request):
    from apps.quizzes import telegram

    if not request.admin_messages or not telegram.is_configured():
        return
    request = BorrowRequest.objects.select_related(
        "reader", "book__author", "copy", "loan", "decided_by"
    ).get(pk=request.pk)
    text = admin_text(request)
    markup = admin_keyboard(request) if request.is_pending else None
    for chat_id, message_id in request.admin_messages:
        if message_id:
            telegram.edit_message(chat_id, message_id, text, reply_markup=markup)


def notify_reader(request):
    from apps.quizzes import telegram
    from apps.quizzes.bot import cabinet_keyboard
    from apps.quizzes.services import reader_chat_id

    chat_id = reader_chat_id(request.reader)
    if not chat_id:
        return
    book = request.book
    if request.status == Status.APPROVED:
        text = (
            f"✅ <b>So'rovingiz tasdiqlandi</b>\n\n"
            f"📚 {book.title}\n"
            f"🔖 Inv. {request.copy.inventory_number}\n"
            f"📅 Qaytarish muddati: <b>{request.loan.due_date:%d.%m.%Y}</b>\n\n"
            "Kitobni o'qib bo'lgach, ilovadagi «Testlar» bo'limidan shu kitob "
            "bo'yicha test topshiring."
        )
    elif request.status == Status.REJECTED:
        text = (
            f"❌ <b>So'rovingiz rad etildi</b>\n\n📚 {book.title}\n"
            + (f"Sabab: {request.reject_reason}\n" if request.reject_reason else "")
            + "\nBatafsil ma'lumot uchun kutubxonachiga murojaat qiling."
        )
    else:
        return
    telegram.safe_send(chat_id, text, reply_markup=cabinet_keyboard(request.reader, chat_id))


def handle_callback(callback):
    """Telegram'dagi «Tasdiqlash / Rad etish» tugmasi bosilganda."""
    from apps.quizzes import telegram

    data = callback.get("data") or ""
    callback_id = callback.get("id")
    user = callback.get("from") or {}
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")

    try:
        _, action, pk = data.split(":", 2)
        pk = int(pk)
    except ValueError:
        telegram.answer_callback(callback_id, "Noma'lum buyruq")
        return

    if not telegram.is_admin_chat(chat_id, user.get("id")):
        telegram.answer_callback(callback_id, "Bu amal faqat kutubxonachi uchun.", show_alert=True)
        return

    request = BorrowRequest.objects.select_related("reader", "book").filter(pk=pk).first()
    if request is None:
        telegram.answer_callback(callback_id, "So'rov topilmadi.", show_alert=True)
        return

    name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
    name = name or (f"@{user['username']}" if user.get("username") else "admin")
    if action == "a":
        ok, text = approve(request, via="telegram", by_name=name)
    elif action == "r":
        ok, text = reject(request, via="telegram", by_name=name)
    else:
        ok, text = False, "Noma'lum amal"

    telegram.answer_callback(callback_id, text, show_alert=not ok)
    if not ok:
        refresh_admin_messages(request)  # eskirgan tugmalarni olib tashlaymiz
