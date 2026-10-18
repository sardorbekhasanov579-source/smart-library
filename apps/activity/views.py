"""12-modul: Ijtimoiy faollik.

Kitobxonning kutubxonadagi faolligi ballanadi: kitob olish, muddatida
qaytarish, test topshirish. Reyting chiqariladi va HEMIS kabi tashqi
tizimga uzatish uchun Excel'ga eksport qilinadi.
"""
import datetime
import logging

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import View

from apps.activity.forms import ManualAwardForm
from apps.activity.models import ActivityKind, ActivityRecord
from apps.activity.services import leaderboard, reader_breakdown, recalc_all
from apps.core.mixins import AdminRequiredMixin, LibrarianRequiredMixin
from apps.core.models import AuditLog
from apps.readers.models import Reader, ReaderType

logger = logging.getLogger(__name__)


def parse_period(request):
    """So'rovdan davrni ajratib oladi. (date_from, date_to, nomi) qaytaradi."""
    preset = request.GET.get("davr", "")
    today = timezone.localdate()

    if preset == "oy":
        return today.replace(day=1), today, "Shu oy"
    if preset == "chorak":
        start_month = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=start_month, day=1), today, "Shu chorak"
    if preset == "yil":
        return today.replace(month=1, day=1), today, "Shu yil"
    if preset == "semestr":
        # Sentyabr-yanvar va fevral-iyun
        if today.month >= 9 or today.month == 1:
            start = today.replace(
                year=today.year if today.month >= 9 else today.year - 1,
                month=9, day=1,
            )
        else:
            start = today.replace(month=2, day=1)
        return start, today, "Shu semestr"

    def _date(name):
        raw = request.GET.get(name, "").strip()
        if not raw:
            return None
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            return None

    date_from, date_to = _date("dan"), _date("gacha")
    if date_from or date_to:
        return date_from, date_to, "Tanlangan davr"
    return None, None, "Butun davr"


class LeaderboardView(LibrarianRequiredMixin, View):
    """Faollik reytingi."""

    template_name = "activity/leaderboard.html"

    def get(self, request):
        date_from, date_to, period_name = parse_period(request)
        reader_type = request.GET.get("type") or ""

        rows = leaderboard(date_from, date_to, reader_type or None)

        totals = {
            "readers": len(rows),
            "points": sum(r["total"] for r in rows),
            "records": ActivityRecord.objects.count(),
        }
        return render(
            request,
            self.template_name,
            {
                "rows": rows[:200],
                "shown": min(len(rows), 200),
                "totals": totals,
                "period_name": period_name,
                "date_from": date_from,
                "date_to": date_to,
                "types": ReaderType.choices,
                "selected_type": reader_type,
                "filters": request.GET,
                "award_form": ManualAwardForm(),
                "kinds": ActivityKind.choices,
            },
        )


class ReaderActivityView(LibrarianRequiredMixin, View):
    """Bitta kitobxonning faollik tarixi."""

    template_name = "activity/reader_detail.html"

    def get(self, request, pk):
        reader = get_object_or_404(Reader, pk=pk)
        date_from, date_to, period_name = parse_period(request)
        data = reader_breakdown(reader, date_from, date_to)

        return render(
            request,
            self.template_name,
            {
                "reader": reader,
                "breakdown": data["rows"],
                "total": data["total"],
                "records": data["records"].select_related(
                    "loan__copy__book", "assignment__quiz__book", "awarded_by"
                )[:200],
                "period_name": period_name,
                "filters": request.GET,
            },
        )


class ManualAwardView(LibrarianRequiredMixin, View):
    """Qo'lda ball berish."""

    def post(self, request):
        form = ManualAwardForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Ball qo'shilmadi — maydonlarni tekshiring.")
            return redirect("activity:leaderboard")

        data = form.cleaned_data
        record = ActivityRecord.objects.create(
            reader=data["reader"],
            kind=ActivityKind.MANUAL,
            points=data["points"],
            happened_at=data["happened_at"],
            note=data["note"],
            awarded_by=request.user if getattr(request.user, "pk", None) else None,
        )
        AuditLog.log(
            user=request.user,
            action=AuditLog.Action.CREATE,
            entity_type="activity",
            entity_id=record.pk,
            details=f"{data['reader'].full_name} ga {data['points']:+d} ball: {data['note']}",
        )
        messages.success(
            request,
            f"{data['reader'].full_name} ga {data['points']:+d} ball qo'shildi.",
        )
        return redirect("activity:reader", pk=data["reader"].pk)


class DeleteRecordView(LibrarianRequiredMixin, View):
    """Qo'lda berilgan ballni o'chirish (avtomatik yozuvlar o'chirilmaydi)."""

    def post(self, request, pk):
        record = get_object_or_404(ActivityRecord, pk=pk)
        reader_id = record.reader_id
        if record.source_key:
            messages.error(
                request,
                "Avtomatik yozuvni o'chirib bo'lmaydi — u qayta hisoblashda "
                "baribir tiklanadi. Ball qiymatini Sozlamalardan o'zgartiring.",
            )
        else:
            record.delete()
            messages.success(request, "Yozuv o'chirildi.")
        return redirect("activity:reader", pk=reader_id)


class RecalcView(AdminRequiredMixin, View):
    """Ballarni qayta hisoblash."""

    def post(self, request):
        try:
            created = recalc_all()
        except Exception as exc:  # pragma: no cover
            logger.exception("Faollik hisoblashda xato")
            messages.error(request, f"Hisoblashda xato: {exc}")
            return redirect("activity:leaderboard")

        messages.success(
            request, f"Qayta hisoblandi. Yangi yozuvlar: {created} ta."
        )
        return redirect("activity:leaderboard")


class ExportView(LibrarianRequiredMixin, View):
    """Reytingni Excel'ga chiqaradi (HEMIS'ga uzatish uchun ham shu format)."""

    def get(self, request):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError:
            messages.error(
                request, "openpyxl o'rnatilmagan — Excel eksport ishlamaydi."
            )
            return redirect("activity:leaderboard")

        date_from, date_to, period_name = parse_period(request)
        reader_type = request.GET.get("type") or ""
        rows = leaderboard(date_from, date_to, reader_type or None)

        wb = Workbook()
        ws = wb.active
        ws.title = "Ijtimoiy faollik"

        header = [
            "O'rin", "HEMIS ID", "Kitobxon kodi", "F.I.Sh.", "Turi",
            "Kitob oldi", "Muddatida qaytardi", "Kechiktirdi",
            "Testdan o'tdi", "A'lo", "Testdan o'tmadi", "Qo'lda",
            "JAMI BALL",
        ]
        ws.append(header)

        head_fill = PatternFill("solid", fgColor="1E3A5F")
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center",
                                       wrap_text=True)

        kind_order = [
            ActivityKind.BORROW, ActivityKind.RETURN_ONTIME, ActivityKind.OVERDUE,
            ActivityKind.QUIZ_PASSED, ActivityKind.QUIZ_PERFECT,
            ActivityKind.QUIZ_FAILED, ActivityKind.MANUAL,
        ]

        for row in rows:
            reader = row["reader"]
            data = reader_breakdown(reader, date_from, date_to)
            by_kind = {item["kind"]: item["total"] for item in data["rows"]}
            ws.append(
                [
                    row["rank"],
                    reader.hemis_id or "",
                    reader.reader_code,
                    reader.full_name,
                    reader.get_reader_type_display(),
                ]
                + [by_kind.get(k, 0) for k in kind_order]
                + [row["total"]]
            )

        widths = [7, 14, 14, 34, 16, 11, 18, 13, 13, 8, 15, 10, 13]
        for index, width in enumerate(widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=index).column_letter].width = width
        ws.freeze_panes = "A2"

        # Sarlavha ostiga davr haqida eslatma
        ws.append([])
        ws.append([f"Davr: {period_name}"])
        if date_from or date_to:
            ws.append(
                [f"{date_from or '...'} — {date_to or '...'}"]
            )
        ws.append([f"Hisobot sanasi: {timezone.localdate():%d.%m.%Y}"])

        filename = f"ijtimoiy_faollik_{timezone.localdate():%Y%m%d}.xlsx"
        response = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response
