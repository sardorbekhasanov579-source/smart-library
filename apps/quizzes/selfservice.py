"""Kitobxonning o'zi bajaradigan amallar (ilova orqali).

  * Bir bosishda kabinetga kirish havolasi (Telegram botdan);
  * kitob uchun testni fonda tayyorlash;
  * olgan kitobini tanlab test boshlash;
  * xato javoblarni AI orqali tahlil qilish — qaysi mavzularni qayta o'qish
    kerakligini aytadi.
"""
import logging
import threading
from datetime import timedelta

from django.core import signing
from django.core.cache import cache
from django.db import close_old_connections
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

LOGIN_SALT = "kabinet-kirish"
LOGIN_MAX_AGE = 60 * 60  # havola 1 soat amal qiladi


# ---------------------------------------------------------------------------
# Kabinetga bir bosishda kirish
# ---------------------------------------------------------------------------
def login_token(reader, chat_id):
    return signing.dumps({"r": reader.pk, "c": int(chat_id)}, salt=LOGIN_SALT, compress=True)


def login_url(reader, chat_id):
    from apps.core.models import SystemSetting

    base = (SystemSetting.get("site_base_url", "") or "").strip().rstrip("/")
    if not base:
        return ""
    return base + reverse("quizzes:magic_login", args=[login_token(reader, chat_id)])


def reader_from_token(token):
    """Havoladagi tokenni tekshiradi. Kitobxon yoki None qaytaradi."""
    from apps.quizzes.models import TelegramAccount
    from apps.readers.models import ReaderStatus

    try:
        data = signing.loads(token, salt=LOGIN_SALT, max_age=LOGIN_MAX_AGE)
    except signing.BadSignature:
        return None
    account = (
        TelegramAccount.objects.select_related("reader")
        .filter(reader_id=data.get("r"), chat_id=data.get("c"), is_verified=True)
        .first()
    )
    if not account or account.reader.status == ReaderStatus.BLOCKED:
        return None
    return account.reader


# ---------------------------------------------------------------------------
# Testni fonda tayyorlash
# ---------------------------------------------------------------------------
def _gen_key(book_id):
    return f"quizgen:{book_id}"


def ready_quiz(book):
    from apps.quizzes.models import Quiz

    quiz = Quiz.objects.filter(book=book, is_active=True).order_by("-created_at").first()
    return quiz if quiz and quiz.is_ready else None


def generation_state(book):
    """'ready' | 'running' | 'failed' | 'idle'"""
    if ready_quiz(book):
        return "ready"
    state = cache.get(_gen_key(book.pk))
    if state in ("running", "failed"):
        return state
    return "idle"


def prepare_quiz_async(book_id):
    """Kitob uchun test bo'lmasa — fonda yaratadi (AI uzoq ishlashi mumkin)."""
    from apps.books.models import Book

    book = Book.objects.filter(pk=book_id).first()
    if not book or ready_quiz(book):
        return
    if not cache.add(_gen_key(book_id), "running", timeout=15 * 60):
        if cache.get(_gen_key(book_id)) == "running":
            return  # boshqa so'rov allaqachon tayyorlayapti
        cache.set(_gen_key(book_id), "running", timeout=15 * 60)

    def task():
        from apps.quizzes.services import get_or_create_quiz

        close_old_connections()
        try:
            quiz, _created, message = get_or_create_quiz(book)
            if quiz and quiz.is_ready:
                cache.delete(_gen_key(book_id))
            else:
                logger.warning("Test tayyor bo'lmadi (%s): %s", book_id, message)
                cache.set(_gen_key(book_id), "failed", timeout=10 * 60)
        except Exception:  # pragma: no cover
            logger.exception("Testni fonda yaratishda xato: %s", book_id)
            cache.set(_gen_key(book_id), "failed", timeout=10 * 60)
        finally:
            close_old_connections()

    threading.Thread(target=task, daemon=True).start()


# ---------------------------------------------------------------------------
# Kitobxon o'zi test boshlashi
# ---------------------------------------------------------------------------
RECENT_RETURN_DAYS = 90


def testable_loans(reader):
    """Test topshirish mumkin bo'lgan kitoblar: qo'lidagilar va yaqinda qaytarganlari."""
    since = timezone.localdate() - timedelta(days=RECENT_RETURN_DAYS)
    loans = (
        reader.loans.select_related("copy__book__author", "copy__book__category")
        .filter(issue_date__gte=since - timedelta(days=365))
        .exclude(return_date__lt=since)
        .order_by("return_date", "-issue_date")
    )
    seen, result = set(), []
    for loan in loans:
        if loan.copy.book_id in seen:
            continue
        seen.add(loan.copy.book_id)
        result.append(loan)
    return result


def assignment_for_loan(loan):
    return loan.quiz_assignments.select_related("quiz").order_by("-created_at").first()


def start_for_loan(reader, loan):
    """(holat, topshiriq) qaytaradi.

    holat: 'ok' — test tayyor, topshiriq qaytadi;
           'preparing' — test fonda tayyorlanmoqda;
           'failed' — test yaratib bo'lmadi;
           'done' — bu kitob bo'yicha test allaqachon yakunlangan.
    """
    from apps.core.models import SystemSetting
    from apps.quizzes.models import Assignment, AssignmentStatus

    existing = assignment_for_loan(loan)
    if existing:
        if existing.can_attempt:
            return "ok", existing
        if existing.is_finished:
            return "done", existing

    book = loan.copy.book
    quiz = ready_quiz(book)
    if quiz is None:
        state = generation_state(book)
        if state == "failed":
            return "failed", None
        prepare_quiz_async(book.pk)
        return "preparing", None

    count = min(SystemSetting.quiz_question_count(), quiz.questions_count)
    assignment = Assignment.objects.create(
        quiz=quiz,
        reader=reader,
        loan=loan,
        question_count=max(count, 1),
        pass_percent=quiz.pass_percent or SystemSetting.quiz_pass_percent(),
        max_attempts=max(1, SystemSetting.get_int("quiz_self_attempts", 2)),
        deadline=timezone.now() + timedelta(days=3),
        status=AssignmentStatus.SENT,
        sent_at=timezone.now(),
        delivery_note="Kitobxon ilovadan o'zi boshladi",
    )
    return "ok", assignment


# ---------------------------------------------------------------------------
# Xato javoblar tahlili
# ---------------------------------------------------------------------------
def wrong_items(attempt):
    items = []
    answers = (
        attempt.answers.select_related("question", "choice")
        .prefetch_related("question__choices")
        .order_by("question__order", "question_id")
    )
    for answer in answers:
        if answer.is_correct:
            continue
        correct = next((c for c in answer.question.choices.all() if c.is_correct), None)
        items.append({
            "question": answer.question.text,
            "given": answer.choice.text if answer.choice_id else "",
            "correct": correct.text if correct else "",
            "explanation": answer.question.explanation,
        })
    return items


def fallback_feedback(attempt, items):
    """AI bo'lmasa: xato qilingan savollarning o'zi — qayta ko'rish uchun."""
    topics = []
    for item in items[:6]:
        text = item["explanation"] or item["question"]
        topics.append(text.strip().rstrip("?")[:160])
    return {
        "status": "done",
        "source": "fallback",
        "summary": (
            f"{attempt.total_questions} ta savoldan {len(items)} tasida xato qilindi. "
            "Quyidagi joylarni kitobdan qayta ko'rib chiqing."
        ),
        "topics": topics,
        "advice": "Shu savollarga tegishli boblarni qayta o'qib, testni yana bir bor ishlang.",
    }


def analyze_attempt(attempt_id):
    """Xatolarni tahlil qilib `attempt.ai_feedback` ga yozadi va kitobxonga yuboradi."""
    from apps.quizzes import ai
    from apps.quizzes.models import Attempt

    attempt = Attempt.objects.select_related(
        "assignment__reader", "assignment__quiz__book__author"
    ).filter(pk=attempt_id).first()
    if not attempt:
        return
    items = wrong_items(attempt)
    if not items:
        feedback = {
            "status": "done", "source": "none",
            "summary": "Barcha savollarga to'g'ri javob berdingiz. Ajoyib natija!",
            "topics": [], "advice": "",
        }
    else:
        feedback = None
        if ai.is_configured():
            try:
                feedback = ai.analyze_mistakes(
                    attempt.assignment.book, items, attempt.percent,
                    attempt.assignment.pass_percent,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("AI tahlil qilmadi: %s", exc)
        if feedback:
            feedback.update({"status": "done", "source": "ai"})
        else:
            feedback = fallback_feedback(attempt, items)

    attempt.ai_feedback = feedback
    attempt.save(update_fields=["ai_feedback"])
    if items:
        send_feedback_to_reader(attempt)


def analyze_attempt_async(attempt):
    attempt.ai_feedback = {"status": "pending"}
    attempt.save(update_fields=["ai_feedback"])

    def task():
        close_old_connections()
        try:
            analyze_attempt(attempt.pk)
        except Exception:  # pragma: no cover
            logger.exception("Tahlil xatosi: %s", attempt.pk)
            from apps.quizzes.models import Attempt

            Attempt.objects.filter(pk=attempt.pk).update(
                ai_feedback={"status": "failed"}
            )
        finally:
            close_old_connections()

    threading.Thread(target=task, daemon=True).start()


def send_feedback_to_reader(attempt):
    from apps.quizzes import telegram
    from apps.quizzes.services import reader_chat_id

    reader = attempt.assignment.reader
    chat_id = reader_chat_id(reader)
    feedback = attempt.ai_feedback or {}
    if not chat_id or feedback.get("status") != "done":
        return
    lines = [
        "🧠 <b>Test tahlili</b>",
        f"📚 {attempt.assignment.book.title} — {attempt.percent}%",
        "",
        feedback.get("summary", ""),
    ]
    if feedback.get("topics"):
        lines += ["", "<b>Qayta o'qish kerak:</b>"]
        lines += [f"• {t}" for t in feedback["topics"][:6]]
    if feedback.get("advice"):
        lines += ["", f"💡 {feedback['advice']}"]
    if attempt.assignment.can_attempt:
        lines += ["", "Tayyor bo'lgach testni yana bir marta ishlashingiz mumkin."]
    telegram.safe_send(chat_id, "\n".join(lines))
