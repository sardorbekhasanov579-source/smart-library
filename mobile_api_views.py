from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.activity.models import ActivityRecord
from apps.activity.services import leaderboard
from apps.books.models import Book
from apps.loans.models import Loan
from apps.quizzes.models import Assignment, AssignmentStatus, Attempt, Question
from apps.readers.models import ReaderStatus
from .permissions import ReaderAccountPermission


def reader_for(request):
    return request.user.reader_profile


def book_payload(book):
    return {
        "id": book.pk,
        "title": book.title,
        "author": book.author.full_name,
        "category": book.category.name,
        "isbn": book.isbn,
        "publisher": book.publisher,
        "publication_year": book.publication_year,
        "description": book.description,
        "total_quantity": book.total_quantity,
        "available_quantity": book.available_quantity,
        "shelf_location": book.shelf_location,
        "cover_url": book.cover.url if book.cover else None,
    }


def assignment_payload(item):
    return {
        "id": item.pk,
        "book_id": item.quiz.book_id,
        "book_title": item.quiz.book.title,
        "quiz_title": item.quiz.title,
        "status": item.status,
        "question_count": item.question_count,
        "pass_percent": item.pass_percent,
        "best_percent": item.best_percent,
        "deadline": item.deadline.isoformat() if item.deadline else None,
        "attempts_used": item.attempts_used,
        "max_attempts": item.max_attempts,
        "can_attempt": item.can_attempt,
    }


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from django.contrib.auth import authenticate
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        user = authenticate(request, username=username, password=password)
        if not user or not user.is_active or getattr(user, "role", None) != "reader":
            return Response({"detail": "Login yoki parol noto'g'ri, yoxud akkaunt faol emas."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            reader = user.reader_profile
        except Exception:
            return Response({"detail": "Bu akkauntga kitobxon profili ulanmagan."}, status=status.HTTP_403_FORBIDDEN)
        if reader.status != ReaderStatus.ACTIVE:
            return Response({"detail": "Kitobxon profili faol emas."}, status=status.HTTP_403_FORBIDDEN)
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {"id": user.pk, "username": user.username, "full_name": reader.full_name},
        })


class MeView(APIView):
    permission_classes = [IsAuthenticated, ReaderAccountPermission]

    def get(self, request):
        reader = reader_for(request)
        loans = reader.loans.all()
        active = loans.filter(return_date__isnull=True)
        activity_total = reader.activity_records.aggregate(total=Sum("points"))["total"] or 0
        ranks = leaderboard(limit=None)
        rank = next((row["rank"] for row in ranks if row["reader"].pk == reader.pk), None)
        return Response({
            "id": reader.pk,
            "full_name": reader.full_name,
            "reader_code": reader.reader_code,
            "hemis_id": reader.hemis_id,
            "email": reader.email,
            "phone": reader.phone,
            "reader_type": reader.reader_type,
            "status": reader.status,
            "registration_date": reader.registration_date.isoformat(),
            "loans_active": active.count(),
            "loans_overdue": sum(1 for loan in active if loan.due_date < timezone.localdate()),
            "social_points": activity_total,
            "social_rank": rank,
        })


class BookListView(APIView):
    permission_classes = [IsAuthenticated, ReaderAccountPermission]

    def get(self, request):
        qs = Book.objects.select_related("author", "category").all()
        query = str(request.query_params.get("q", "")).strip()
        category = request.query_params.get("category")
        available = request.query_params.get("available")
        if query:
            from django.db.models import Q
            qs = qs.filter(Q(title__icontains=query) | Q(author__full_name__icontains=query) | Q(isbn__icontains=query))
        if category and category.isdigit():
            qs = qs.filter(category_id=int(category))
        if available in {"1", "true", "yes"}:
            qs = qs.filter(available_quantity__gt=0)
        page = max(int(request.query_params.get("page", 1) or 1), 1)
        page_size = min(max(int(request.query_params.get("page_size", 20) or 20), 1), 50)
        total = qs.count()
        start = (page - 1) * page_size
        return Response({"count": total, "page": page, "page_size": page_size, "results": [book_payload(b) for b in qs[start:start + page_size]]})


class BookDetailView(APIView):
    permission_classes = [IsAuthenticated, ReaderAccountPermission]

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        book = get_object_or_404(Book.objects.select_related("author", "category").prefetch_related("copies"), pk=pk)
        data = book_payload(book)
        data["copies"] = [{"inventory_number": c.inventory_number, "status": c.status, "shelf_location": c.shelf_location} for c in book.copies.all()]
        return Response(data)


class MyLoansView(APIView):
    permission_classes = [IsAuthenticated, ReaderAccountPermission]

    def get(self, request):
        reader = reader_for(request)
        qs = Loan.objects.filter(reader=reader).select_related("copy__book", "copy__book__author").order_by("-issue_date")
        return Response([{
            "id": loan.pk,
            "book_title": loan.copy.book.title,
            "author": loan.copy.book.author.full_name,
            "inventory_number": loan.copy.inventory_number,
            "shelf_location": loan.copy.shelf_location,
            "issue_date": loan.issue_date.isoformat(),
            "due_date": loan.due_date.isoformat(),
            "return_date": loan.return_date.isoformat() if loan.return_date else None,
            "status": loan.effective_status(),
            "is_overdue": loan.is_overdue,
        } for loan in qs])


class MyActivityView(APIView):
    permission_classes = [IsAuthenticated, ReaderAccountPermission]

    def get(self, request):
        reader = reader_for(request)
        qs = ActivityRecord.objects.filter(reader=reader).select_related("loan", "assignment")
        rows = list(qs[:100])
        total = qs.aggregate(total=Sum("points"))["total"] or 0
        return Response({
            "total_points": total,
            "history": [{"id": r.pk, "kind": r.kind, "label": r.get_kind_display(), "points": r.points, "date": r.happened_at.isoformat(), "note": r.note} for r in rows],
        })


class LeaderboardView(APIView):
    permission_classes = [IsAuthenticated, ReaderAccountPermission]

    def get(self, request):
        period = request.query_params.get("period", "all")
        today = timezone.localdate()
        date_from = date_to = None
        if period == "month":
            date_from, date_to = today.replace(day=1), today
        elif period == "year":
            date_from, date_to = today.replace(month=1, day=1), today
        rows = leaderboard(date_from=date_from, date_to=date_to, limit=100)
        return Response({"period": period, "results": [{"rank": r["rank"], "reader_id": r["reader"].pk, "full_name": r["reader"].full_name, "points": r["total"]} for r in rows]})


class MyAssignmentsView(APIView):
    permission_classes = [IsAuthenticated, ReaderAccountPermission]

    def get(self, request):
        qs = Assignment.objects.filter(reader=reader_for(request)).select_related("quiz__book").prefetch_related("attempts")
        return Response([assignment_payload(item) for item in qs])


class StartAttemptView(APIView):
    permission_classes = [IsAuthenticated, ReaderAccountPermission]

    @transaction.atomic
    def post(self, request, assignment_id):
        from django.shortcuts import get_object_or_404
        item = get_object_or_404(Assignment.objects.select_for_update().select_related("quiz__book"), pk=assignment_id, reader=reader_for(request))
        if item.is_expired:
            item.status = AssignmentStatus.EXPIRED
            item.finished_at = timezone.now()
            item.save(update_fields=["status", "finished_at"])
            return Response({"detail": "Test topshirish muddati o'tgan."}, status=status.HTTP_400_BAD_REQUEST)
        if not item.can_attempt:
            return Response({"detail": "Bu testni boshlash mumkin emas."}, status=status.HTTP_400_BAD_REQUEST)
        open_attempt = item.attempts.filter(finished_at__isnull=True).first()
        if open_attempt:
            attempt = open_attempt
        else:
            ids = item.quiz.pick_question_ids(item.question_count)
            if not ids:
                return Response({"detail": "Testda savollar mavjud emas."}, status=status.HTTP_400_BAD_REQUEST)
            attempt = Attempt.objects.create(assignment=item, question_ids=ids, total_questions=len(ids))
        item.status = AssignmentStatus.STARTED
        item.save(update_fields=["status"])
        questions = []
        for question in attempt.questions():
            questions.append({"id": question.pk, "text": question.text, "choices": [{"id": c.pk, "text": c.text} for c in question.shuffled_choices()]})
        return Response({"attempt_id": attempt.pk, "assignment_id": item.pk, "started_at": attempt.started_at.isoformat(), "deadline": item.deadline.isoformat() if item.deadline else None, "questions": questions})


class SubmitAttemptView(APIView):
    permission_classes = [IsAuthenticated, ReaderAccountPermission]

    @transaction.atomic
    def post(self, request, attempt_id):
        from django.shortcuts import get_object_or_404
        attempt = get_object_or_404(Attempt.objects.select_for_update().select_related("assignment"), pk=attempt_id, assignment__reader=reader_for(request))
        if attempt.finished_at:
            return Response({"detail": "Bu urinish allaqachon yakunlangan.", "percent": attempt.percent, "passed": attempt.passed}, status=status.HTTP_409_CONFLICT)
        assignment = attempt.assignment
        if assignment.is_expired:
            return Response({"detail": "Test topshirish muddati o'tgan."}, status=status.HTTP_400_BAD_REQUEST)
        raw_answers = request.data.get("answers", {})
        if not isinstance(raw_answers, dict):
            return Response({"detail": "answers obyekt ko'rinishida bo'lishi kerak."}, status=status.HTTP_400_BAD_REQUEST)
        allowed_ids = set(attempt.question_ids or [])
        posted = {}
        for question_id, choice_id in raw_answers.items():
            try:
                qid, cid = int(question_id), int(choice_id)
            except (TypeError, ValueError):
                return Response({"detail": "Savol yoki javob ID noto'g'ri."}, status=status.HTTP_400_BAD_REQUEST)
            if qid not in allowed_ids:
                return Response({"detail": "Bu savol ushbu urinishga tegishli emas."}, status=status.HTTP_400_BAD_REQUEST)
            if not Question.objects.filter(pk=qid, choices__pk=cid).exists():
                return Response({"detail": "Javob varianti ushbu savolga tegishli emas."}, status=status.HTTP_400_BAD_REQUEST)
            posted[qid] = cid
        attempt.grade(posted)
        # Mavjud ijtimoiy faollik mexanizmini ishga tushiramiz; source_key dublikatdan himoya qiladi.
        from apps.activity.services import recalc_quizzes
        recalc_quizzes(Assignment.objects.filter(pk=assignment.pk))
        return Response({"attempt_id": attempt.pk, "percent": attempt.percent, "correct_count": attempt.correct_count, "total_questions": attempt.total_questions, "passed": attempt.passed, "finished_at": attempt.finished_at.isoformat()})
