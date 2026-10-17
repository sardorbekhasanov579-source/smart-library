"""3-modul: Kitobxonlar - ro'yxatga olish va boshqarish."""
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from apps.core.mixins import AuditLogMixin, LibrarianRequiredMixin
from apps.core.models import AuditLog
from apps.readers.forms import ReaderForm
from apps.readers.models import Reader, ReaderStatus


class ReaderListView(LibrarianRequiredMixin, ListView):
    model = Reader
    template_name = "readers/reader_list.html"
    context_object_name = "readers"
    paginate_by = 20

    def get_queryset(self):
        qs = Reader.objects.annotate(
            loans_active=Count("loans", filter=Q(loans__return_date__isnull=True))
        )
        params = self.request.GET
        q = params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(full_name__icontains=q)
                | Q(reader_code__icontains=q)
                | Q(phone__icontains=q)
                | Q(email__icontains=q)
            )
        status = params.get("status")
        if status:
            qs = qs.filter(status=status)
        reader_type = params.get("type")
        if reader_type:
            qs = qs.filter(reader_type=reader_type)
        if params.get("debtors") == "1":
            qs = qs.filter(
                loans__return_date__isnull=True,
                loans__due_date__lt=timezone.localdate(),
            ).distinct()
        return qs.order_by("full_name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filters"] = self.request.GET
        ctx["statuses"] = ReaderStatus.choices
        ctx["types"] = Reader._meta.get_field("reader_type").choices
        ctx["total_count"] = self.get_queryset().count()
        return ctx


class ReaderDetailView(LibrarianRequiredMixin, DetailView):
    model = Reader
    template_name = "readers/reader_detail.html"
    context_object_name = "reader"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        loans = self.object.loans.select_related("copy__book", "issued_by")
        ctx["active_loans"] = loans.filter(return_date__isnull=True).order_by("due_date")
        ctx["history"] = loans.filter(return_date__isnull=False).order_by("-return_date")[:30]
        ctx["total_loans"] = loans.count()
        ctx["overdue_count"] = self.object.overdue_loans_count
        return ctx


class ReaderCreateView(LibrarianRequiredMixin, AuditLogMixin, CreateView):
    model = Reader
    form_class = ReaderForm
    template_name = "readers/reader_form.html"
    audit_entity = "reader"

    def get_initial(self):
        initial = super().get_initial()
        initial["reader_code"] = Reader.generate_code()
        return initial

    def get_success_url(self):
        messages.success(
            self.request,
            f"{self.object.full_name} ro'yxatga olindi. Kodi: {self.object.reader_code}",
        )
        return self.object.get_absolute_url()


class ReaderUpdateView(LibrarianRequiredMixin, AuditLogMixin, UpdateView):
    model = Reader
    form_class = ReaderForm
    template_name = "readers/reader_form.html"
    audit_entity = "reader"

    def get_success_url(self):
        messages.success(self.request, "Kitobxon ma'lumotlari yangilandi.")
        return self.object.get_absolute_url()


class ReaderDeleteView(LibrarianRequiredMixin, DeleteView):
    model = Reader
    template_name = "readers/reader_confirm_delete.html"
    success_url = reverse_lazy("readers:list")

    def form_valid(self, form):
        reader = self.get_object()
        if reader.active_loans_count:
            messages.error(request=self.request,
                           message="Qo'lida kitob bor kitobxonni o'chirib bo'lmaydi.")
            return redirect(reader.get_absolute_url())
        if reader.loans.exists():
            reader.status = ReaderStatus.ARCHIVED
            reader.save(update_fields=["status"])
            messages.info(self.request, "Tarixi borligi uchun kitobxon arxivlandi.")
            return redirect(reader.get_absolute_url())
        AuditLog.log(user=self.request.user, action=AuditLog.Action.DELETE,
                     entity_type="reader", entity_id=reader.pk, details=str(reader))
        messages.success(self.request, "Kitobxon o'chirildi.")
        return super().form_valid(form)


class ReaderToggleStatusView(LibrarianRequiredMixin, View):
    """Kitobxonni bloklash / blokdan chiqarish."""

    def post(self, request, pk):
        reader = get_object_or_404(Reader, pk=pk)
        if reader.status == ReaderStatus.ACTIVE:
            reader.status = ReaderStatus.BLOCKED
            text = "bloklandi"
        else:
            reader.status = ReaderStatus.ACTIVE
            text = "faollashtirildi"
        reader.save(update_fields=["status"])
        AuditLog.log(user=request.user, action=AuditLog.Action.UPDATE,
                     entity_type="reader", entity_id=reader.pk,
                     details=f"{reader.full_name} {text}")
        messages.success(request, f"{reader.full_name} {text}.")
        return redirect(reader.get_absolute_url())
