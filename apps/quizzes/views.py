"""11-modul: Testlar.

Ikki qism bor:
  * Kutubxonachi/admin uchun: testlar ro'yxati, savollarni tahrirlash,
    topshiriqlar va natijalar, Telegram sozlamalari.
  * Kitobxon uchun: Telegramdan kelgan maxfiy havola orqali testni yechish
    hamda telefon + kod bilan shaxsiy kabinetga kirish.
"""
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView, View

from apps.books.models import Book, BookCopy
from apps.core.mixins import AdminRequiredMixin, LibrarianRequiredMixin
from apps.core.models import SystemSetting
from apps.quizzes import ai, telegram
from apps.quizzes.forms import (
    AssignmentCreateForm,
    CodeForm,
    PhoneForm,
    QuestionForm,
    QuizSettingsForm,
    TestMessageForm,
)
from apps.quizzes.models import (
    Assignment,
    AssignmentStatus,
    Attempt,
    OtpCode,
    Question,
    Quiz,
    TelegramAccount,
)
from apps.quizzes.services import (
    get_or_create_quiz,
    log_quiz_event,
    notify_admins_result,
    send_assignment,
    send_login_code,
)
from apps.quizzes.utils import pretty_phone
from apps.readers.models import Reader

logger = logging.getLogger(__name__)

SESSION_KEY = "quiz_reader_id"
SESSION_PHONE = "quiz_login_phone"


# ===========================================================================
# KUTUBXONACHI / ADMIN
# ===========================================================================
class QuizListView(LibrarianRequiredMixin, ListView):
    """Testlar ro'yxati."""

    template_name = "quizzes/quiz_list.html"
    context_object_name = "quizzes"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Quiz.objects.select_related("book__author")
            .annotate(
                q_count=Count("questions", distinct=True),
                a_count=Count("assignments", distinct=True),
            )
        )
        params = self.request.GET
        query = params.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(book__title__icontains=query)
                | Q(book__author__full_name__icontains=query)
            )
        source = params.get("source")
        if source:
            qs = qs.filter(source=source)
        if params.get("weak") == "1":
            qs = qs.filter(q_count__lt=5)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filters"] = self.request.GET
        ctx["sources"] = Quiz._meta.get_field("source").choices
        ctx["total_count"] = self.get_queryset().count()
        ctx["ai_ready"] = ai.is_configured()
        ctx["ai_provider"] = ai.get_provider()
        ctx["tg_ready"] = telegram.is_configured()
        ctx["stat_assignments"] = Assignment.objects.count()
        ctx["stat_passed"] = Assignment.objects.filter(
            status=AssignmentStatus.PASSED
        ).count()
        ctx["stat_failed"] = Assignment.objects.filter(
            status__in=[AssignmentStatus.FAILED, AssignmentStatus.EXPIRED]
        ).count()
        ctx["stat_open"] = Assignment.objects.filter(
            status__in=[AssignmentStatus.PENDING, AssignmentStatus.SENT,
                        AssignmentStatus.STARTED]
        ).count()

        # Kitob qidirish (test tuzish uchun)
        book_query = self.request.GET.get("book", "").strip()
        ctx["book_query"] = book_query
        if book_query:
            ctx["found_books"] = (
                Book.objects.select_related("author")
                .filter(
                    Q(title__icontains=book_query)
                    | Q(author__full_name__icontains=book_query)
                    | Q(isbn__icontains=book_query)
                )
                .annotate(quiz_count=Count("quizzes"))
                .order_by("title")[:15]
            )
        return ctx


class QuizGenerateView(LibrarianRequiredMixin, View):
    """Kitob uchun test to'plamini yaratish (AI yoki zaxira generator)."""

    def post(self, request):
        book_id = request.POST.get("book_id")
        book = get_object_or_404(Book, pk=book_id)
        force = request.POST.get("force") == "1"
        try:
            quiz, created, message = get_or_create_quiz(book, user=request.user, force=force)
        except Exception as exc:  # pragma: no cover
            logger.exception("Test yaratishda xato")
            messages.error(request, f"Test yaratilmadi: {exc}")
            return redirect("quizzes:quiz_list")

        if not quiz:
            messages.error(request, message or "Test yaratilmadi.")
            return redirect("quizzes:quiz_list")

        log_quiz_event(
            request.user,
            f"'{book.title}' uchun test {'yaratildi' if created else 'ishlatildi'}: {message}",
            quiz.pk,
        )
        if quiz.questions_count < 5:
            messages.warning(
                request,
                f"Test tuzildi, lekin faqat {quiz.questions_count} ta savol bor. {message} "
                "Savollarni qo'lda to'ldiring.",
            )
        else:
            messages.success(request, f"{quiz.questions_count} ta savol tayyor. {message}")
        return redirect(quiz.get_absolute_url())


class QuizDetailView(LibrarianRequiredMixin, DetailView):
    """Test savollari va sozlamalari."""

    model = Quiz
    template_name = "quizzes/quiz_detail.html"
    context_object_name = "quiz"

    def get_queryset(self):
        return Quiz.objects.select_related("book__author", "book__category", "created_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        quiz = self.object
        ctx["questions"] = quiz.questions.prefetch_related("choices")
        ctx["question_form"] = kwargs.get("question_form") or QuestionForm()
        ctx["settings_form"] = kwargs.get("settings_form") or QuizSettingsForm(
            initial={
                "title": quiz.title,
                "question_target": quiz.question_target,
                "pass_percent": quiz.pass_percent,
                "is_active": quiz.is_active,
            }
        )
        ctx["assignments"] = (
            quiz.assignments.select_related("reader").order_by("-created_at")[:20]
        )
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        action = request.POST.get("action")

        if action == "add_question":
            form = QuestionForm(request.POST)
            if form.is_valid():
                form.save(self.object)
                messages.success(request, "Savol qo'shildi.")
                return redirect(self.object.get_absolute_url())
            messages.error(request, "Savolni saqlab bo'lmadi, maydonlarni tekshiring.")
            return self.render_to_response(
                self.get_context_data(object=self.object, question_form=form)
            )

        if action == "save_settings":
            form = QuizSettingsForm(request.POST)
            if form.is_valid():
                quiz = self.object
                quiz.title = form.cleaned_data["title"] or quiz.title
                quiz.question_target = form.cleaned_data["question_target"]
                quiz.pass_percent = form.cleaned_data["pass_percent"]
                quiz.is_active = form.cleaned_data["is_active"]
                quiz.save()
                messages.success(request, "Sozlamalar saqlandi.")
                return redirect(quiz.get_absolute_url())
            messages.error(request, "Sozlamalarni saqlab bo'lmadi.")
            return self.render_to_response(
                self.get_context_data(object=self.object, settings_form=form)
            )

        messages.error(request, "Noma'lum amal.")
        return redirect(self.object.get_absolute_url())


class QuestionEditView(LibrarianRequiredMixin, View):
    """Savolni tahrirlash."""

    template_name = "quizzes/question_form.html"

    def get(self, request, pk):
        question = self.get_question(pk)
        return render(
            request,
            self.template_name,
            {"question": question, "quiz": question.quiz, "form": QuestionForm(instance=question)},
        )

    def post(self, request, pk):
        question = self.get_question(pk)
        form = QuestionForm(request.POST, instance=question)
        if form.is_valid():
            form.save(question.quiz)
            messages.success(request, "Savol yangilandi.")
            return redirect(question.quiz.get_absolute_url())
        return render(
            request,
            self.template_name,
            {"question": question, "quiz": question.quiz, "form": form},
        )

    def get_question(self, pk):
        return get_object_or_404(
            Question.objects.select_related("quiz__book"), pk=pk
        )


class QuestionDeleteView(LibrarianRequiredMixin, View):
    def post(self, request, pk):
        question = get_object_or_404(Question.objects.select_related("quiz"), pk=pk)
        quiz = question.quiz
        question.delete()
        messages.success(request, "Savol o'chirildi.")
        return redirect(quiz.get_absolute_url())


class QuizDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        quiz = get_object_or_404(Quiz, pk=pk)
        if quiz.assignments.exists():
            quiz.is_active = False
            quiz.save(update_fields=["is_active"])
            messages.warning(
                request,
                "Bu testda topshiriqlar bor — o'chirilmadi, faqat nofaol holatga o'tdi.",
            )
        else:
            title = str(quiz)
            quiz.delete()
            messages.success(request, f"«{title}» o'chirildi.")
        return redirect("quizzes:quiz_list")


class AssignmentListView(LibrarianRequiredMixin, ListView):
    """Topshiriqlar va natijalar."""

    template_name = "quizzes/assignment_list.html"
    context_object_name = "assignments"
    paginate_by = 25

    def get_queryset(self):
        qs = Assignment.objects.select_related(
            "reader", "quiz__book__author", "loan"
        )
        params = self.request.GET
        query = params.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(reader__full_name__icontains=query)
                | Q(reader__reader_code__icontains=query)
                | Q(quiz__book__title__icontains=query)
            )
        status = params.get("status")
        if status:
            qs = qs.filter(status=status)
        if params.get("open") == "1":
            qs = qs.filter(
                status__in=[AssignmentStatus.PENDING, AssignmentStatus.SENT,
                            AssignmentStatus.STARTED]
            )
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filters"] = self.request.GET
        ctx["statuses"] = AssignmentStatus.choices
        ctx["total_count"] = self.get_queryset().count()
        ctx["create_form"] = AssignmentCreateForm()
        return ctx


class AssignmentCreateView(LibrarianRequiredMixin, View):
    """Testni qo'lda biriktirish."""

    def post(self, request):
        form = AssignmentCreateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Operatsiya tanlanmadi yoki ma'lumot xato.")
            return redirect("quizzes:assignment_list")

        loan = form.cleaned_data["loan"]
        quiz, _created, message = get_or_create_quiz(loan.copy.book, user=request.user)
        if not quiz or not quiz.is_ready:
            messages.error(
                request,
                f"«{loan.copy.book.title}» uchun test tayyor emas. {message} "
                "Savollarni to'ldirib, keyin qayta urinib ko'ring.",
            )
            return redirect("quizzes:assignment_list")

        assignment = Assignment.create_for_loan(
            loan,
            quiz,
            question_count=form.cleaned_data.get("question_count"),
            pass_percent=form.cleaned_data.get("pass_percent"),
        )
        log_quiz_event(
            request.user,
            f"{loan.reader.full_name} ga '{loan.copy.book.title}' testi biriktirildi",
            assignment.pk,
        )

        if form.cleaned_data.get("send_now"):
            ok, note = send_assignment(assignment)
            if ok:
                messages.success(request, "Topshiriq yaratildi va Telegramga yuborildi.")
            else:
                messages.warning(
                    request,
                    f"Topshiriq yaratildi, lekin yuborilmadi: {note} "
                    f"Havolani qo'lda bering: {assignment.absolute_link()}",
                )
        else:
            messages.success(request, "Topshiriq yaratildi.")
        return redirect("quizzes:assignment_detail", pk=assignment.pk)


class AssignmentDetailView(LibrarianRequiredMixin, DetailView):
    model = Assignment
    template_name = "quizzes/assignment_detail.html"
    context_object_name = "assignment"

    def get_queryset(self):
        return Assignment.objects.select_related(
            "reader", "quiz__book__author", "loan__copy__book"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["attempts"] = self.object.attempts.order_by("-started_at")
        ctx["link"] = self.object.absolute_link()
        ctx["has_telegram"] = TelegramAccount.objects.filter(
            reader=self.object.reader, is_verified=True
        ).exists()
        return ctx


class AssignmentSendView(LibrarianRequiredMixin, View):
    """Topshiriqni (qayta) Telegram orqali yuborish."""

    def post(self, request, pk):
        assignment = get_object_or_404(
            Assignment.objects.select_related("reader", "quiz__book__author"), pk=pk
        )
        ok, note = send_assignment(assignment)
        if ok:
            messages.success(request, "Telegram orqali yuborildi.")
        else:
            messages.error(request, f"Yuborilmadi: {note}")
        return redirect("quizzes:assignment_detail", pk=pk)


class AttemptDetailView(LibrarianRequiredMixin, DetailView):
    """Urinishdagi javoblarni ko'rish."""

    model = Attempt
    template_name = "quizzes/attempt_detail.html"
    context_object_name = "attempt"

    def get_queryset(self):
        return Attempt.objects.select_related(
            "assignment__reader", "assignment__quiz__book"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["answers"] = (
            self.object.answers.select_related("question", "choice")
            .prefetch_related("question__choices")
            .order_by("question__order", "question_id")
        )
        return ctx


class TelegramPanelView(AdminRequiredMixin, TemplateView):
    """Telegram va AI sozlamalarini tekshirish paneli."""

    template_name = "quizzes/telegram_panel.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tg_configured"] = telegram.is_configured()
        ctx["admin_chats"] = telegram.admin_chat_ids()
        ctx["ai_configured"] = ai.is_configured()
        ctx["ai_provider"] = ai.get_provider()
        ctx["ai_model"] = ai.get_model()
        ctx["base_url"] = SystemSetting.get("site_base_url", "") or "—"
        ctx["days_before"] = SystemSetting.quiz_days_before_due()
        ctx["pass_percent"] = SystemSetting.quiz_pass_percent()
        ctx["question_count"] = SystemSetting.quiz_question_count()
        ctx["accounts"] = (
            TelegramAccount.objects.select_related("reader").order_by("-created_at")[:50]
        )
        ctx["accounts_total"] = TelegramAccount.objects.count()
        ctx["readers_total"] = Reader.objects.count()
        ctx["form"] = kwargs.get("form") or TestMessageForm()

        if ctx["tg_configured"]:
            try:
                me = telegram.get_me()
                ctx["bot_username"] = me.get("username")
                ctx["bot_name"] = me.get("first_name")
            except telegram.TelegramError as exc:
                ctx["bot_error"] = str(exc)
        return ctx

    def post(self, request, *args, **kwargs):
        form = TestMessageForm(request.POST)
        if form.is_valid():
            ok, error = telegram.safe_send(
                form.cleaned_data["chat_id"], form.cleaned_data["text"]
            )
            if ok:
                messages.success(request, "Sinov xabari yuborildi.")
            else:
                messages.error(request, f"Yuborilmadi: {error}")
            return redirect("quizzes:telegram_panel")
        return self.render_to_response(self.get_context_data(form=form))


# ===========================================================================
# KITOBXON — maxfiy havola orqali test yechish
# ===========================================================================
class TakeQuizView(View):
    """Telegramdan kelgan havola orqali testni yechish (login talab qilmaydi)."""

    template_name = "quizzes/take.html"

    def get_assignment(self, token):
        assignment = (
            Assignment.objects.select_related("reader", "quiz__book__author", "loan")
            .filter(token=token)
            .first()
        )
        if not assignment:
            raise Http404("Test topilmadi")
        return assignment

    def get(self, request, token):
        assignment = self.get_assignment(token)

        if assignment.is_expired and not assignment.is_finished:
            return render(
                request,
                "quizzes/closed.html",
                {"assignment": assignment, "reason": "expired"},
            )
        if assignment.status == AssignmentStatus.PASSED or (
            assignment.is_finished and not assignment.can_attempt
        ):
            return redirect("quizzes:result", token=token)

        attempt = assignment.attempts.filter(finished_at__isnull=True).first()
        if attempt is None:
            if not assignment.can_attempt:
                return redirect("quizzes:result", token=token)
            ids = assignment.quiz.pick_question_ids(assignment.question_count)
            if not ids:
                return render(
                    request,
                    "quizzes/closed.html",
                    {"assignment": assignment, "reason": "no_questions"},
                )
            attempt = Attempt.objects.create(assignment=assignment, question_ids=ids)
            if assignment.status in {AssignmentStatus.PENDING, AssignmentStatus.SENT}:
                assignment.status = AssignmentStatus.STARTED
                assignment.save(update_fields=["status"])

        questions = attempt.questions()
        return render(
            request,
            self.template_name,
            {
                "assignment": assignment,
                "attempt": attempt,
                "questions": questions,
                "total": len(questions),
            },
        )

    def post(self, request, token):
        assignment = self.get_assignment(token)
        attempt = assignment.attempts.filter(finished_at__isnull=True).first()
        if attempt is None:
            messages.error(request, "Bu test allaqachon yakunlangan.")
            return redirect("quizzes:result", token=token)

        if assignment.is_expired:
            return render(
                request,
                "quizzes/closed.html",
                {"assignment": assignment, "reason": "expired"},
            )

        posted = {}
        unanswered = 0
        for question in attempt.questions():
            raw = request.POST.get(f"q_{question.id}")
            if raw:
                try:
                    posted[question.id] = int(raw)
                except (TypeError, ValueError):
                    unanswered += 1
            else:
                unanswered += 1

        if unanswered and request.POST.get("confirm") != "1":
            questions = attempt.questions()
            messages.warning(
                request,
                f"{unanswered} ta savol javobsiz qoldi. "
                "Yakunlashni istasangiz yana bir marta «Yakunlash» tugmasini bosing.",
            )
            return render(
                request,
                self.template_name,
                {
                    "assignment": assignment,
                    "attempt": attempt,
                    "questions": questions,
                    "total": len(questions),
                    "selected": posted,
                    "confirm": True,
                },
            )

        attempt.grade(posted)
        try:
            notify_admins_result(assignment, attempt)
        except Exception:  # pragma: no cover
            logger.exception("Natija adminga yuborilmadi: %s", assignment.pk)
        self.notify_reader(assignment, attempt)
        return redirect("quizzes:result", token=token)

    @staticmethod
    def notify_reader(assignment, attempt):
        from apps.quizzes.services import reader_chat_id

        chat_id = reader_chat_id(assignment.reader)
        if not chat_id:
            return
        if attempt.passed:
            text = (
                f"✅ <b>Test topshirildi!</b>\n\n"
                f"📚 {assignment.book.title}\n"
                f"📊 Natija: <b>{attempt.percent}%</b> "
                f"({attempt.correct_count}/{attempt.total_questions})\n\n"
                "Rahmat! Kutubxonachiga ham xabar yuborildi."
            )
        else:
            text = (
                f"❌ <b>Test o'tmadi</b>\n\n"
                f"📚 {assignment.book.title}\n"
                f"📊 Natija: <b>{attempt.percent}%</b> "
                f"({attempt.correct_count}/{attempt.total_questions})\n"
                f"Kerakli chegara: {assignment.pass_percent}%\n\n"
                "Kitobni yana bir ko'rib chiqishni tavsiya qilamiz."
            )
        telegram.safe_send(chat_id, text)


class QuizResultView(View):
    """Test natijasi."""

    def get(self, request, token):
        assignment = get_object_or_404(
            Assignment.objects.select_related("reader", "quiz__book__author"), token=token
        )
        attempt = assignment.attempts.filter(finished_at__isnull=False).order_by(
            "-finished_at"
        ).first()
        answers = []
        if attempt:
            answers = (
                attempt.answers.select_related("question", "choice")
                .prefetch_related("question__choices")
                .order_by("question__order", "question_id")
            )
        return render(
            request,
            "quizzes/result.html",
            {
                "assignment": assignment,
                "attempt": attempt,
                "answers": answers,
                "show_answers": SystemSetting.get("quiz_show_answers", "1") == "1",
            },
        )


# ===========================================================================
# KITOBXON — telefon + Telegram kodi bilan kabinet
# ===========================================================================
class ReaderLoginView(View):
    """1-qadam: telefon raqam, 2-qadam: Telegramdan kelgan kod."""

    template_name = "quizzes/login.html"

    def _render(self, request, **context):
        """Barcha holatlarda bot havolasi ko'rinib tursin."""
        context.setdefault("bot_link", telegram.bot_link())
        context.setdefault("bot_username", telegram.bot_username())
        return render(request, self.template_name, context)

    def get(self, request):
        if request.session.get(SESSION_KEY):
            return redirect("quizzes:portal")
        phone = request.session.get(SESSION_PHONE)
        return self._render(
            request,
            phone_form=PhoneForm(initial={"phone": phone}),
            code_form=CodeForm() if phone else None,
            step=2 if phone else 1,
            phone=pretty_phone(phone) if phone else "",
        )

    def post(self, request):
        step = request.POST.get("step")

        if step == "phone":
            form = PhoneForm(request.POST)
            if form.is_valid():
                phone = form.cleaned_data["phone"]
                ok, message = send_login_code(phone)
                if ok:
                    request.session[SESSION_PHONE] = phone
                    messages.success(request, message)
                    return redirect("quizzes:login")
                messages.error(request, message)
            return self._render(request, phone_form=form, code_form=None, step=1)

        if step == "code":
            phone = request.session.get(SESSION_PHONE)
            form = CodeForm(request.POST)
            if not phone:
                messages.error(request, "Avval telefon raqamni kiriting.")
                return redirect("quizzes:login")
            if form.is_valid():
                ok, message, otp = OtpCode.check_code(phone, form.cleaned_data["code"])
                if ok and otp and otp.reader_id:
                    request.session[SESSION_KEY] = otp.reader_id
                    request.session.pop(SESSION_PHONE, None)
                    return redirect("quizzes:portal")
                messages.error(request, message or "Kod tasdiqlanmadi.")
            return self._render(
                request,
                phone_form=PhoneForm(initial={"phone": phone}),
                code_form=form,
                step=2,
                phone=pretty_phone(phone),
            )

        if step == "resend":
            phone = request.session.get(SESSION_PHONE)
            if phone:
                ok, message = send_login_code(phone)
                if ok:
                    messages.success(request, message)
                else:
                    messages.error(request, message)
            return redirect("quizzes:login")

        if step == "reset":
            request.session.pop(SESSION_PHONE, None)
            return redirect("quizzes:login")

        return redirect("quizzes:login")


# ---------------------------------------------------------------------------
# Kitobxon ilovasi — 4 bo'lim:
#   1) Mening sahifam   2) Kitoblar bazasi   3) Testlarim   4) Sozlamalar
# ---------------------------------------------------------------------------
FINISHED_STATUSES = (
    AssignmentStatus.PASSED,
    AssignmentStatus.FAILED,
    AssignmentStatus.EXPIRED,
)


class ReaderPageMixin:
    """Sessiyadagi kitobxonni aniqlaydi va umumiy kontekstni beradi.

    Kitobxon telefon + Telegram kodi bilan kiradi, shuning uchun Django
    `login_required` emas, sessiyadagi `SESSION_KEY` ishlatiladi.
    """

    tab = ""

    def dispatch(self, request, *args, **kwargs):
        reader_id = request.session.get(SESSION_KEY)
        if not reader_id:
            return redirect("quizzes:login")
        reader = Reader.objects.filter(pk=reader_id).first()
        if not reader:
            request.session.pop(SESSION_KEY, None)
            return redirect("quizzes:login")
        self.reader = reader
        return super().dispatch(request, *args, **kwargs)

    def telegram_account(self):
        return TelegramAccount.objects.filter(reader=self.reader).first()

    def open_quiz_count(self):
        return (
            self.reader.quiz_assignments.exclude(status__in=FINISHED_STATUSES).count()
        )

    def page_context(self, **extra):
        context = {
            "reader": self.reader,
            "tab": self.tab,
            "today": timezone.localdate(),
            "open_quiz_count": self.open_quiz_count(),
        }
        context.update(extra)
        return context


class ReaderPortalView(ReaderPageMixin, View):
    """1-bo'lim: kitobxon haqida ma'lumot va qo'lidagi kitoblar."""

    template_name = "quizzes/portal.html"
    tab = "home"

    def get(self, request):
        reader = self.reader

        loans = list(
            reader.loans.select_related("copy__book__author", "copy__book__category")
            .filter(return_date__isnull=True)
            .order_by("due_date")
        )
        returned_count = reader.loans.filter(return_date__isnull=False).count()
        overdue_count = sum(1 for loan in loans if loan.is_overdue)
        self._mark_deadlines(loans)

        assignments = list(
            reader.quiz_assignments.select_related("quiz__book__author").order_by(
                "-created_at"
            )[:6]
        )
        open_assignments = [a for a in assignments if not a.is_finished]
        passed_count = reader.quiz_assignments.filter(
            status=AssignmentStatus.PASSED
        ).count()

        # Ijtimoiy faollik balli va reytingdagi o'rni (ikki so'rov)
        points, rank = self._activity(reader)

        return render(
            request,
            self.template_name,
            self.page_context(
                loans=loans,
                loans_count=len(loans),
                returned_count=returned_count,
                overdue_count=overdue_count,
                passed_count=passed_count,
                open_assignments=open_assignments,
                telegram=self.telegram_account(),
                points=points,
                rank=rank,
                level=reader.level,
                max_books=reader.book_limit,
            ),
        )

    @staticmethod
    def _mark_deadlines(loans):
        """Har bir kitob uchun muddat chizig'i va rangini hisoblaydi."""
        today = timezone.localdate()
        for loan in loans:
            total = (loan.due_date - loan.issue_date).days or 1
            left = (loan.due_date - today).days
            passed = max(total - max(left, 0), 0)
            loan.bar_percent = min(100, max(4, round(passed * 100 / total)))
            loan.days_remaining = left
            if left < 0:
                loan.bar_state = "bad"
                loan.deadline_text = f"{abs(left)} kun kechikdi"
            elif left == 0:
                loan.bar_state = "warn"
                loan.deadline_text = "Bugun qaytarish kerak"
            elif left <= 2:
                loan.bar_state = "warn"
                loan.deadline_text = f"{left} kun qoldi"
            else:
                loan.bar_state = ""
                loan.deadline_text = f"{left} kun qoldi"
            loan.shelf = loan.copy.shelf_location or loan.copy.book.shelf_location

    @staticmethod
    def _activity(reader):
        """Kitobxonning umumiy balli va reytingdagi o'rni."""
        try:
            from django.db.models import Sum

            from apps.activity.models import ActivityRecord
        except ImportError:  # faollik moduli o'chirilgan bo'lsa
            return None, None

        points = reader.activity_records.aggregate(s=Sum("points"))["s"]
        if points is None:
            return None, None
        better = (
            ActivityRecord.objects.values("reader_id")
            .annotate(total=Sum("points"))
            .filter(total__gt=points)
            .count()
        )
        return points, better + 1


class ReaderBooksView(ReaderPageMixin, View):
    """2-bo'lim: kutubxona fondini qidirish va kitob qayerda turganini ko'rish."""

    template_name = "quizzes/reader_books.html"
    tab = "books"
    per_page = 15

    def get(self, request):
        query = (request.GET.get("q") or "").strip()
        only = (request.GET.get("holat") or "").strip()  # "" | "mavjud"

        books = Book.objects.select_related("author", "category")
        if query:
            books = books.filter(
                Q(title__icontains=query)
                | Q(author__full_name__icontains=query)
                | Q(category__name__icontains=query)
                | Q(isbn__icontains=query)
                | Q(publisher__icontains=query)
                | Q(copies__inventory_number__icontains=query)
            ).distinct()
        if only == "mavjud":
            books = books.filter(available_quantity__gt=0)
        books = books.order_by("title")

        # Qidiruv bo'lmasa butun fondni emas, faqat yangi qo'shilganlarini
        if not query and not only:
            books = Book.objects.select_related("author", "category").order_by(
                "-created_at"
            )

        paginator = Paginator(books, self.per_page)
        page = paginator.get_page(request.GET.get("sahifa"))

        # Har bir kitobning nusxalari — javon manzili bilan
        copies_by_book = {}
        if page.object_list:
            copies = (
                BookCopy.objects.filter(book__in=list(page.object_list))
                .order_by("inventory_number")
            )
            for copy in copies:
                copies_by_book.setdefault(copy.book_id, []).append(copy)

        return render(
            request,
            self.template_name,
            self.page_context(
                query=query,
                only=only,
                page=page,
                total=paginator.count,
                copies_by_book=copies_by_book,
                is_search=bool(query or only),
                fond_total=Book.objects.count(),
            ),
        )


class ReaderQuizzesView(ReaderPageMixin, View):
    """3-bo'lim: kitobxonga biriktirilgan testlar."""

    template_name = "quizzes/reader_quizzes.html"
    tab = "quizzes"

    def get(self, request):
        shown = (request.GET.get("holat") or "faol").strip()

        all_assignments = list(
            self.reader.quiz_assignments.select_related(
                "quiz__book__author"
            ).order_by("-created_at")
        )
        open_list = [a for a in all_assignments if not a.is_finished]
        done_list = [a for a in all_assignments if a.is_finished]

        if shown == "yakunlangan":
            items = done_list
        elif shown == "hammasi":
            items = all_assignments
        else:
            shown = "faol"
            items = open_list

        passed = [a for a in done_list if a.status == AssignmentStatus.PASSED]
        best = max((a.best_percent for a in done_list), default=0)

        return render(
            request,
            self.template_name,
            self.page_context(
                items=items,
                shown=shown,
                open_count=len(open_list),
                done_count=len(done_list),
                all_count=len(all_assignments),
                passed_count=len(passed),
                best_percent=best,
                now=timezone.now(),
                quiz_pass_percent=SystemSetting.quiz_pass_percent(),
            ),
        )


class ReaderSettingsView(ReaderPageMixin, View):
    """4-bo'lim: sozlamalar — Telegram, bildirishnomalar, ko'rinish, yordam."""

    template_name = "quizzes/reader_settings.html"
    tab = "settings"

    def get(self, request):
        return render(request, self.template_name, self._context())

    def post(self, request):
        action = request.POST.get("amal")
        account = self.telegram_account()

        if action == "bildirishnoma":
            if not account:
                messages.error(request, "Telegram hisobi ulanmagan.")
            else:
                account.notifications_enabled = request.POST.get("yoq") == "1"
                account.save(update_fields=["notifications_enabled"])
                messages.success(
                    request,
                    "Bildirishnomalar yoqildi."
                    if account.notifications_enabled
                    else "Bildirishnomalar o'chirildi.",
                )
        elif action == "telegram_uzish":
            if account:
                account.delete()
                messages.success(
                    request,
                    "Telegram hisobi ajratildi. Qayta ulash uchun botga /start "
                    "yuboring.",
                )
            else:
                messages.info(request, "Ulangan Telegram hisobi yo'q edi.")
        else:
            messages.error(request, "Noma'lum amal.")

        return redirect("quizzes:reader_settings")

    def _context(self):
        account = self.telegram_account()
        try:
            from apps.activity.levels import level_table

            levels = level_table()
        except ImportError:
            levels = []
        return self.page_context(
            telegram=account,
            level=self.reader.level,
            levels=levels,
            bot_link=telegram.bot_link(),
            bot_username=telegram.bot_username(),
            library_phone=SystemSetting.get("library_phone", ""),
            library_hours=SystemSetting.get("library_hours", ""),
            library_name=SystemSetting.library_name(),
            quiz_pass_percent=SystemSetting.quiz_pass_percent(),
            loan_days=self.reader.loan_days,
            max_books=self.reader.book_limit,
        )


class ReaderLogoutView(View):
    def post(self, request):
        request.session.pop(SESSION_KEY, None)
        request.session.pop(SESSION_PHONE, None)
        return redirect("quizzes:login")

    def get(self, request):
        return self.post(request)


# ===========================================================================
# Kichik API (kitob kartasidan test holatini ko'rish uchun)
# ===========================================================================
class BookQuizStatusView(LibrarianRequiredMixin, View):
    def get(self, request, book_id):
        quiz = (
            Quiz.objects.filter(book_id=book_id, is_active=True)
            .annotate(q_count=Count("questions"))
            .order_by("-created_at")
            .first()
        )
        if not quiz:
            return JsonResponse({"exists": False})
        return JsonResponse(
            {
                "exists": True,
                "quiz_id": quiz.pk,
                "questions": quiz.q_count,
                "ready": quiz.is_ready,
                "url": reverse("quizzes:quiz_detail", args=[quiz.pk]),
            }
        )
