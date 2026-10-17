"""4-modul: Kitob berish, 5-modul: Kitob qaytarish, hamda operatsiyalar ro'yxati.

7-bo'limdagi ishlash algoritmi:
  Kitobxonni qidirish -> Kitobni qidirish (mavjud nusxani tanlash) ->
  Berish sanasi va muddatini kiritish -> Operatsiyani saqlash ->
  Nusxa statusini "berilgan" ga o'zgartirish.
"""
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import DetailView, ListView, View

from apps.books.models import Book, BookCopy, CopyStatus
from apps.core.mixins import LibrarianRequiredMixin
from apps.loans.forms import IssueForm, ReturnForm
from apps.loans.models import Loan, LoanStatus
from apps.readers.models import Reader


class LoanListView(LibrarianRequiredMixin, ListView):
    """Barcha berish/qaytarish operatsiyalari."""

    model = Loan
    template_name = "loans/loan_list.html"
    context_object_name = "loans"
    paginate_by = 25

    def get_queryset(self):
        qs = Loan.objects.select_related("reader", "copy__book", "issued_by")
        params = self.request.GET
        q = params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(reader__full_name__icontains=q)
                | Q(reader__reader_code__icontains=q)
                | Q(copy__book__title__icontains=q)
                | Q(copy__inventory_number__icontains=q)
            )
        status = params.get("status")
        today = timezone.localdate()
        if status == LoanStatus.ISSUED:
            qs = qs.filter(return_date__isnull=True, due_date__gte=today)
        elif status == LoanStatus.OVERDUE:
            qs = qs.filter(return_date__isnull=True, due_date__lt=today)
        elif status == LoanStatus.RETURNED:
            qs = qs.filter(return_date__isnull=False)
        elif status == LoanStatus.LOST:
            qs = qs.filter(status=LoanStatus.LOST)

        date_from = params.get("from")
        date_to = params.get("to")
        if date_from:
            qs = qs.filter(issue_date__gte=date_from)
        if date_to:
            qs = qs.filter(issue_date__lte=date_to)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx["filters"] = self.request.GET
        ctx["statuses"] = LoanStatus.choices
        ctx["count_active"] = Loan.objects.filter(return_date__isnull=True).count()
        ctx["count_overdue"] = Loan.objects.filter(
            return_date__isnull=True, due_date__lt=today
        ).count()
        ctx["count_today"] = Loan.objects.filter(issue_date=today).count()
        return ctx


class LoanDetailView(LibrarianRequiredMixin, DetailView):
    model = Loan
    template_name = "loans/loan_detail.html"
    context_object_name = "loan"

    def get_queryset(self):
        return Loan.objects.select_related(
            "reader", "copy__book__author", "issued_by", "received_by"
        )


class IssueBookView(LibrarianRequiredMixin, View):
    """4-modul: Kitob berishni qayd etish."""

    template_name = "loans/issue.html"

    def get(self, request):
        initial = {}
        reader = self._find_reader(request.GET.get("reader"))
        copy = self._find_copy(request.GET.get("copy"))
        if not copy and request.GET.get("book"):
            copy = (
                BookCopy.objects.filter(
                    book_id=request.GET["book"], status=CopyStatus.AVAILABLE
                ).select_related("book").first()
            )
        if reader:
            initial["reader"] = reader.pk
        if copy:
            initial["copy"] = copy.pk
        form = IssueForm(initial=initial)
        return render(request, self.template_name, self._context(form, reader, copy))

    def post(self, request):
        form = IssueForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Formani to'ldirishda xatolik bor.")
            return render(request, self.template_name, self._context(form))

        reader = form.cleaned_data["reader"]
        copy = form.cleaned_data["copy"]
        try:
            loan = Loan.issue(
                reader=reader,
                copy=copy,
                user=request.user,
                days=form.cleaned_data["days"],
                note=form.cleaned_data.get("note", ""),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, self._context(form, reader, copy))

        messages.success(
            request,
            f"'{copy.book.title}' {reader.full_name} ga berildi. "
            f"Qaytarish muddati: {loan.due_date:%d.%m.%Y}",
        )
        return redirect("loans:detail", pk=loan.pk)

    # -- yordamchilar ----------------------------------------------------
    def _context(self, form, reader=None, copy=None):
        today = timezone.localdate()
        return {
            "form": form,
            "selected_reader": reader,
            "selected_copy": copy,
            "recent": Loan.objects.select_related("reader", "copy__book")
            .filter(issue_date=today)
            .order_by("-created_at")[:10],
            "today_count": Loan.objects.filter(issue_date=today).count(),
        }

    @staticmethod
    def _find_reader(value):
        if not value:
            return None
        return Reader.objects.filter(Q(pk=value) if str(value).isdigit()
                                     else Q(reader_code__iexact=value)).first()

    @staticmethod
    def _find_copy(value):
        if not value:
            return None
        if str(value).isdigit():
            return BookCopy.objects.filter(pk=value).first()
        return BookCopy.objects.filter(
            Q(inventory_number__iexact=value) | Q(qr_code__iexact=value)
        ).first()


class ReturnBookView(LibrarianRequiredMixin, View):
    """5-modul: Kitob qaytarib olish."""

    template_name = "loans/return.html"

    def get(self, request):
        query = request.GET.get("q", "").strip()
        loans = Loan.objects.select_related("reader", "copy__book").filter(
            return_date__isnull=True
        )
        if query:
            loans = loans.filter(
                Q(copy__inventory_number__iexact=query)
                | Q(copy__qr_code__iexact=query)
                | Q(reader__reader_code__iexact=query)
                | Q(reader__full_name__icontains=query)
                | Q(copy__book__title__icontains=query)
            )
        return render(
            request,
            self.template_name,
            {
                "query": query,
                "loans": loans.order_by("due_date")[:50],
                "form": ReturnForm(),
                "today_returned": Loan.objects.filter(
                    return_date=timezone.localdate()
                ).count(),
            },
        )

    def post(self, request):
        loan = get_object_or_404(Loan, pk=request.POST.get("loan_id"))
        form = ReturnForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Qaytarish formasida xatolik.")
            return redirect("loans:return")
        try:
            loan.give_back(
                user=request.user,
                condition=form.cleaned_data["condition"],
                note=form.cleaned_data.get("note", ""),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("loans:return")

        if loan.status == LoanStatus.LOST:
            messages.warning(
                request, f"'{loan.copy.book.title}' yo'qolgan deb belgilandi."
            )
        elif loan.overdue_days:
            messages.warning(
                request,
                f"Qaytarildi, lekin {loan.overdue_days} kun kechikkan: "
                f"{loan.copy.book.title}",
            )
        else:
            messages.success(request, f"'{loan.copy.book.title}' qaytarib olindi.")
        return redirect("loans:return")


class ExtendLoanView(LibrarianRequiredMixin, View):
    """Qaytarish muddatini uzaytirish."""

    def post(self, request, pk):
        loan = get_object_or_404(Loan, pk=pk)
        try:
            days = int(request.POST.get("days", 7))
        except ValueError:
            days = 7
        try:
            loan.extend(days=max(1, min(days, 90)), user=request.user)
            messages.success(
                request, f"Muddat {days} kunga uzaytirildi: {loan.due_date:%d.%m.%Y}"
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("loans:detail", pk=loan.pk)


class OverdueListView(LibrarianRequiredMixin, ListView):
    """Muddati o'tgan kitoblar ro'yxati (qarzdorlar)."""

    model = Loan
    template_name = "loans/overdue_list.html"
    context_object_name = "loans"
    paginate_by = 30

    def get_queryset(self):
        return (
            Loan.objects.select_related("reader", "copy__book")
            .filter(return_date__isnull=True, due_date__lt=timezone.localdate())
            .order_by("due_date")
        )


class CopyLookupView(LibrarianRequiredMixin, View):
    """Inventar raqami yoki QR kod bo'yicha nusxani topish (AJAX/qo'lda)."""

    def get(self, request):
        from django.http import JsonResponse

        code = request.GET.get("code", "").strip()
        copy = (
            BookCopy.objects.select_related("book")
            .filter(Q(inventory_number__iexact=code) | Q(qr_code__iexact=code))
            .first()
        )
        if not copy:
            return JsonResponse({"found": False, "message": "Nusxa topilmadi"})
        return JsonResponse(
            {
                "found": True,
                "id": copy.pk,
                "title": copy.book.title,
                "author": copy.book.author.full_name,
                "inventory_number": copy.inventory_number,
                "status": copy.get_status_display(),
                "available": copy.status == CopyStatus.AVAILABLE,
            }
        )
