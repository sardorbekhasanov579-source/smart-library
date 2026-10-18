"""Faollik ballarini hisoblash."""
import logging

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.activity.models import ActivityKind, ActivityRecord, points_for

logger = logging.getLogger(__name__)


def _award(reader, kind, source_key, happened_at, loan=None, assignment=None, note=""):
    """Bitta ball yozuvini yaratadi. Allaqachon bo'lsa qayta yaratmaydi.

    (yaratildimi, yozuv) qaytaradi.
    """
    points = points_for(kind)
    if points == 0 and kind != ActivityKind.MANUAL:
        # Ball 0 bo'lsa yozuv saqlashning ma'nosi yo'q
        ActivityRecord.objects.filter(source_key=source_key).delete()
        return False, None

    record, created = ActivityRecord.objects.get_or_create(
        source_key=source_key,
        defaults={
            "reader": reader,
            "kind": kind,
            "points": points,
            "happened_at": happened_at,
            "loan": loan,
            "assignment": assignment,
            "note": note,
        },
    )
    # Sozlamadagi ball o'zgargan bo'lsa yangilaymiz
    if not created and record.points != points:
        record.points = points
        record.save(update_fields=["points"])
    return created, record


@transaction.atomic
def recalc_loans(queryset=None):
    """Kitob berish/qaytarish bo'yicha ballarni hisoblaydi."""
    from apps.loans.models import Loan

    loans = queryset if queryset is not None else Loan.objects.all()
    loans = loans.select_related("reader")
    created = 0

    for loan in loans.iterator():
        # Kitob olgani uchun
        ok, _ = _award(
            loan.reader,
            ActivityKind.BORROW,
            f"loan:{loan.pk}:borrow",
            loan.issue_date,
            loan=loan,
        )
        created += int(ok)

        if not loan.return_date:
            continue

        if loan.return_date <= loan.due_date:
            ok, _ = _award(
                loan.reader,
                ActivityKind.RETURN_ONTIME,
                f"loan:{loan.pk}:ontime",
                loan.return_date,
                loan=loan,
            )
        else:
            kechikish = (loan.return_date - loan.due_date).days
            ok, _ = _award(
                loan.reader,
                ActivityKind.OVERDUE,
                f"loan:{loan.pk}:overdue",
                loan.return_date,
                loan=loan,
                note=f"{kechikish} kun kechikdi",
            )
        created += int(ok)

    return created


@transaction.atomic
def recalc_quizzes(queryset=None):
    """Test natijalari bo'yicha ballarni hisoblaydi."""
    from apps.quizzes.models import Assignment, AssignmentStatus

    items = queryset if queryset is not None else Assignment.objects.all()
    items = items.select_related("reader", "quiz__book")
    created = 0

    for item in items.iterator():
        moment = item.finished_at or item.deadline or item.created_at
        when = timezone.localtime(moment).date()
        book_title = item.quiz.book.title if item.quiz_id else ""

        if item.status == AssignmentStatus.PASSED:
            ok, _ = _award(
                item.reader,
                ActivityKind.QUIZ_PASSED,
                f"quiz:{item.pk}:passed",
                when,
                assignment=item,
                note=book_title[:200],
            )
            created += int(ok)

            if item.best_percent >= 100:
                ok, _ = _award(
                    item.reader,
                    ActivityKind.QUIZ_PERFECT,
                    f"quiz:{item.pk}:perfect",
                    when,
                    assignment=item,
                    note=book_title[:200],
                )
                created += int(ok)

        elif item.status in (AssignmentStatus.FAILED, AssignmentStatus.EXPIRED):
            ok, _ = _award(
                item.reader,
                ActivityKind.QUIZ_FAILED,
                f"quiz:{item.pk}:failed",
                when,
                assignment=item,
                note=book_title[:200],
            )
            created += int(ok)

    return created


def recalc_all():
    """Hammasini qayta hisoblaydi. Takroran ishga tushirish xavfsiz."""
    return recalc_loans() + recalc_quizzes()


# ---------------------------------------------------------------------------
# Reyting
# ---------------------------------------------------------------------------
def leaderboard(date_from=None, date_to=None, reader_type=None, limit=None):
    """Kitobxonlarni ball bo'yicha tartiblab qaytaradi."""
    from apps.readers.models import Reader, ReaderStatus

    records = ActivityRecord.objects.all()
    if date_from:
        records = records.filter(happened_at__gte=date_from)
    if date_to:
        records = records.filter(happened_at__lte=date_to)

    totals = (
        records.values("reader_id")
        .annotate(total=Sum("points"))
        .order_by("-total")
    )
    score_map = {row["reader_id"]: row["total"] or 0 for row in totals}
    if not score_map:
        return []

    readers = Reader.objects.filter(pk__in=score_map).exclude(
        status=ReaderStatus.ARCHIVED
    )
    if reader_type:
        readers = readers.filter(reader_type=reader_type)

    rows = [
        {"reader": reader, "total": score_map.get(reader.pk, 0)} for reader in readers
    ]
    rows.sort(key=lambda r: (-r["total"], r["reader"].full_name))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows[:limit] if limit else rows


def reader_breakdown(reader, date_from=None, date_to=None):
    """Bitta kitobxon uchun ballarning turlar bo'yicha taqsimoti."""
    records = reader.activity_records.all()
    if date_from:
        records = records.filter(happened_at__gte=date_from)
    if date_to:
        records = records.filter(happened_at__lte=date_to)

    labels = dict(ActivityKind.choices)
    rows = []
    for item in records.values("kind").annotate(total=Sum("points")).order_by("-total"):
        rows.append(
            {
                "kind": item["kind"],
                "label": labels.get(item["kind"], item["kind"]),
                "total": item["total"] or 0,
                "count": records.filter(kind=item["kind"]).count(),
            }
        )
    total = records.aggregate(s=Sum("points"))["s"] or 0
    return {"rows": rows, "total": total, "records": records}
