"""1-modul: Dashboard (umumiy statistika), 6-modul: Qidiruv, 10-modul: Sozlamalar."""
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.generic import TemplateView, View

from apps.books.models import Book, BookCopy, CopyStatus
from apps.catalog.models import Author, Category
from apps.core.mixins import AdminRequiredMixin, AnyRoleMixin
from apps.core.models import AuditLog, SystemSetting
from apps.loans.models import Loan, LoanStatus
from apps.readers.models import Reader, ReaderStatus

UZ_MONTHS = ["Yan", "Fev", "Mar", "Apr", "May", "Iyn", "Iyl", "Avg", "Sen", "Okt", "Noy", "Dek"]


class DashboardView(AnyRoleMixin, TemplateView):
    """Bosh sahifa - mockupdagi statistika kartalari, oylik grafik va so'nggi amallar."""

    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        user = self.request.user

        # Kitobxon faqat o'z ma'lumotlarini ko'radi
        if user.is_reader:
            reader = getattr(user, "reader_profile", None)
            ctx["reader"] = reader
            if reader:
                ctx["my_loans"] = (
                    reader.loans.select_related("copy__book")
                    .filter(return_date__isnull=True)
                    .order_by("due_date")
                )
                ctx["my_history"] = (
                    reader.loans.select_related("copy__book")
                    .filter(return_date__isnull=False)
                    .order_by("-return_date")[:10]
                )
            return ctx

        copies = BookCopy.objects.all()
        active_loans = Loan.objects.filter(return_date__isnull=True)

        ctx["stat_total_books"] = copies.exclude(
            status__in=[CopyStatus.WRITTEN_OFF, CopyStatus.LOST]
        ).count()
        ctx["stat_total_titles"] = Book.objects.count()
        ctx["stat_total_readers"] = Reader.objects.filter(status=ReaderStatus.ACTIVE).count()
        ctx["stat_issued"] = active_loans.count()
        ctx["stat_available"] = copies.filter(status=CopyStatus.AVAILABLE).count()
        ctx["stat_overdue"] = active_loans.filter(due_date__lt=today).count()
        ctx["stat_today_issued"] = Loan.objects.filter(issue_date=today).count()
        ctx["stat_today_returned"] = Loan.objects.filter(return_date=today).count()

        # Oylik statistika (so'nggi 12 oy) - mockupdagi ustunli diagramma
        year_ago = today - timedelta(days=365)
        monthly = (
            Loan.objects.filter(issue_date__gte=year_ago)
            .annotate(month=TruncMonth("issue_date"))
            .values("month")
            .annotate(total=Count("id"))
            .order_by("month")
        )
        counts = {row["month"].strftime("%Y-%m"): row["total"] for row in monthly if row["month"]}
        chart = []
        cursor = today.replace(day=1) - timedelta(days=334)
        cursor = cursor.replace(day=1)
        for _ in range(12):
            key = cursor.strftime("%Y-%m")
            chart.append({"label": UZ_MONTHS[cursor.month - 1], "value": counts.get(key, 0)})
            cursor = (cursor.replace(day=28) + timedelta(days=5)).replace(day=1)
        max_value = max([c["value"] for c in chart] + [1])
        for item in chart:
            item["percent"] = round(item["value"] * 100 / max_value)
        ctx["chart"] = chart
        ctx["chart_max"] = max_value

        # So'nggi operatsiyalar lentasi
        ctx["recent_logs"] = (
            AuditLog.objects.select_related("user")
            .exclude(action__in=[AuditLog.Action.LOGIN, AuditLog.Action.LOGOUT])[:8]
        )
        # Diqqat talab qiladigan ro'yxat
        ctx["overdue_loans"] = (
            active_loans.select_related("reader", "copy__book")
            .filter(due_date__lt=today)
            .order_by("due_date")[:8]
        )
        ctx["top_books"] = (
            Book.objects.annotate(loans_count=Count("copies__loans"))
            .filter(loans_count__gt=0)
            .order_by("-loans_count")[:5]
        )
        return ctx


class GlobalSearchView(AnyRoleMixin, TemplateView):
    """6-modul: Qidiruv - kitob, muallif yoki ISBN bo'yicha umumiy qidiruv."""

    template_name = "core/search.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        ctx["query"] = query
        if not query:
            return ctx

        ctx["books"] = (
            Book.objects.select_related("author", "category")
            .filter(
                Q(title__icontains=query)
                | Q(isbn__icontains=query)
                | Q(author__full_name__icontains=query)
                | Q(publisher__icontains=query)
            )[:25]
        )
        ctx["authors"] = Author.objects.filter(full_name__icontains=query)[:10]
        ctx["categories"] = Category.objects.filter(name__icontains=query)[:10]
        ctx["copies"] = (
            BookCopy.objects.select_related("book")
            .filter(Q(inventory_number__icontains=query) | Q(qr_code__iexact=query))[:10]
        )
        if self.request.user.can_manage_library():
            ctx["readers"] = Reader.objects.filter(
                Q(full_name__icontains=query)
                | Q(reader_code__icontains=query)
                | Q(phone__icontains=query)
            )[:10]
        ctx["total_found"] = sum(
            len(ctx.get(key, [])) for key in ("books", "authors", "categories", "copies", "readers")
        )
        return ctx


class SettingsView(AdminRequiredMixin, View):
    """10-modul: Sozlamalar - tizim parametrlarini boshqarish."""

    template_name = "core/settings.html"

    def get(self, request):
        return render(request, self.template_name, {"settings": self._all()})

    def post(self, request):
        updated = 0
        for item in self._all():
            field = f"setting_{item.key}"
            if field in request.POST:
                new_value = request.POST[field].strip()
                if new_value != item.value:
                    SystemSetting.set(item.key, new_value, item.description)
                    updated += 1
        if updated:
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.UPDATE,
                entity_type="settings",
                details=f"{updated} ta sozlama o'zgartirildi",
            )
            messages.success(request, f"{updated} ta sozlama saqlandi.")
        else:
            messages.info(request, "O'zgarish kiritilmadi.")
        return redirect("core:settings")

    def _all(self):
        existing = {s.key for s in SystemSetting.objects.all()}
        for key, value, desc in SystemSetting.defaults():
            if key not in existing:
                SystemSetting.set(key, value, desc)
        return SystemSetting.objects.all()


class AuditLogView(AdminRequiredMixin, TemplateView):
    """Amallar jurnali (audit_logs)."""

    template_name = "core/audit_log.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        logs = AuditLog.objects.select_related("user")
        action = self.request.GET.get("action", "")
        if action:
            logs = logs.filter(action=action)
        ctx["logs"] = logs[:200]
        ctx["actions"] = AuditLog.Action.choices
        ctx["selected_action"] = action
        return ctx


def handler403(request, exception=None):
    return render(request, "core/403.html", status=403)


def handler404(request, exception=None):
    return render(request, "core/404.html", status=404)
