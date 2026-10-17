"""2-modul: Kitoblar - kitoblar va nusxalarni boshqarish."""
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView, View,
)

from apps.books.forms import BookCopyBulkForm, BookCopyForm, BookForm
from apps.books.models import Book, BookCopy, CopyStatus
from apps.catalog.models import Author, Category
from apps.core.mixins import AnyRoleMixin, AuditLogMixin, LibrarianRequiredMixin
from apps.core.models import AuditLog


class BookListView(AnyRoleMixin, ListView):
    """Kitoblar ro'yxati: qidiruv, toifa/muallif/holat bo'yicha filtr, sahifalash."""

    model = Book
    template_name = "books/book_list.html"
    context_object_name = "books"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Book.objects.select_related("author", "category")
            .annotate(copies_total=Count("copies", distinct=True))
        )
        params = self.request.GET
        q = params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(isbn__icontains=q)
                | Q(author__full_name__icontains=q)
                | Q(publisher__icontains=q)
            )
        category_id = params.get("category")
        if category_id:
            category = Category.objects.filter(pk=category_id).first()
            if category:
                qs = qs.filter(category_id__in=category.all_descendant_ids())
        author_id = params.get("author")
        if author_id:
            qs = qs.filter(author_id=author_id)
        availability = params.get("availability")
        if availability == "available":
            qs = qs.filter(available_quantity__gt=0)
        elif availability == "out":
            qs = qs.filter(available_quantity=0)

        order = params.get("order", "title")
        allowed = {"title", "-title", "-created_at", "created_at",
                   "-available_quantity", "available_quantity"}
        return qs.order_by(order if order in allowed else "title")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = Category.objects.select_related("parent").all()
        ctx["authors"] = Author.objects.all()
        ctx["filters"] = self.request.GET
        ctx["total_count"] = self.get_queryset().count()
        return ctx


class BookDetailView(AnyRoleMixin, DetailView):
    model = Book
    template_name = "books/book_detail.html"
    context_object_name = "book"

    def get_queryset(self):
        return Book.objects.select_related("author", "category")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.loans.models import Loan

        ctx["copies"] = self.object.copies.all().order_by("inventory_number")
        if self.request.user.can_manage_library():
            ctx["loan_history"] = (
                Loan.objects.select_related("reader", "copy")
                .filter(copy__book=self.object)
                .order_by("-created_at")[:15]
            )
        else:
            ctx["loan_history"] = []
        ctx["copy_form"] = BookCopyForm(initial={"book": self.object})
        ctx["bulk_form"] = BookCopyBulkForm()
        return ctx


class BookCreateView(LibrarianRequiredMixin, AuditLogMixin, CreateView):
    model = Book
    form_class = BookForm
    template_name = "books/book_form.html"
    audit_entity = "book"

    def get_success_url(self):
        messages.success(self.request, f"'{self.object.title}' kitobi qo'shildi.")
        return self.object.get_absolute_url()


class BookUpdateView(LibrarianRequiredMixin, AuditLogMixin, UpdateView):
    model = Book
    form_class = BookForm
    template_name = "books/book_form.html"
    audit_entity = "book"

    def get_success_url(self):
        messages.success(self.request, "Kitob ma'lumotlari yangilandi.")
        return self.object.get_absolute_url()


class BookDeleteView(LibrarianRequiredMixin, DeleteView):
    model = Book
    template_name = "books/book_confirm_delete.html"
    success_url = reverse_lazy("books:list")

    def form_valid(self, form):
        book = self.get_object()
        if book.copies.filter(status=CopyStatus.ISSUED).exists():
            messages.error(
                self.request,
                "Bu kitobning berilgan nusxalari bor. Avval ularni qaytarib oling.",
            )
            return redirect(book.get_absolute_url())
        AuditLog.log(
            user=self.request.user,
            action=AuditLog.Action.DELETE,
            entity_type="book",
            entity_id=book.pk,
            details=f"'{book.title}' kitobi o'chirildi",
        )
        messages.success(self.request, f"'{book.title}' o'chirildi.")
        return super().form_valid(form)


# --- Nusxalar -------------------------------------------------------------
class BookCopyCreateView(LibrarianRequiredMixin, View):
    """Kitobga bitta nusxa qo'shish."""

    def post(self, request, pk):
        book = get_object_or_404(Book, pk=pk)
        form = BookCopyForm(request.POST)
        if form.is_valid():
            copy = form.save(commit=False)
            copy.book = book
            copy.save()
            book.recalc_quantities()
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.CREATE,
                entity_type="book_copy",
                entity_id=copy.pk,
                details=f"'{book.title}' uchun nusxa qo'shildi: {copy.inventory_number}",
            )
            messages.success(request, f"Nusxa qo'shildi: {copy.inventory_number}")
        else:
            messages.error(request, f"Xatolik: {form.errors.as_text()}")
        return redirect(book.get_absolute_url())


class BookCopyBulkCreateView(LibrarianRequiredMixin, View):
    """Bir vaqtda bir nechta nusxa yaratish (inventar raqamlari avtomatik)."""

    def post(self, request, pk):
        book = get_object_or_404(Book, pk=pk)
        form = BookCopyBulkForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Nusxa sonini to'g'ri kiriting.")
            return redirect(book.get_absolute_url())

        count = form.cleaned_data["count"]
        prefix = form.cleaned_data.get("prefix") or f"INV-{book.pk:04d}"
        created = []
        start = book.copies.count() + 1
        for i in range(count):
            number = f"{prefix}-{start + i:03d}"
            while BookCopy.objects.filter(inventory_number=number).exists():
                start += 1
                number = f"{prefix}-{start + i:03d}"
            created.append(
                BookCopy.objects.create(
                    book=book,
                    inventory_number=number,
                    shelf_location=book.shelf_location,
                )
            )
        book.recalc_quantities()
        AuditLog.log(
            user=request.user,
            action=AuditLog.Action.CREATE,
            entity_type="book_copy",
            entity_id=book.pk,
            details=f"'{book.title}' uchun {len(created)} ta nusxa qo'shildi",
        )
        messages.success(request, f"{len(created)} ta nusxa qo'shildi.")
        return redirect(book.get_absolute_url())


class BookCopyUpdateView(LibrarianRequiredMixin, UpdateView):
    model = BookCopy
    form_class = BookCopyForm
    template_name = "books/copy_form.html"

    def get_success_url(self):
        self.object.book.recalc_quantities()
        messages.success(self.request, "Nusxa holati yangilandi.")
        return self.object.book.get_absolute_url()


class BookCopyDeleteView(LibrarianRequiredMixin, View):
    def post(self, request, pk):
        copy = get_object_or_404(BookCopy, pk=pk)
        book = copy.book
        if copy.status == CopyStatus.ISSUED:
            messages.error(request, "Berilgan nusxani o'chirib bo'lmaydi.")
        elif copy.loans.exists():
            copy.status = CopyStatus.WRITTEN_OFF
            copy.save(update_fields=["status"])
            messages.info(request, "Nusxa tarixi borligi uchun hisobdan chiqarildi.")
        else:
            number = copy.inventory_number
            copy.delete()
            messages.success(request, f"Nusxa o'chirildi: {number}")
        book.recalc_quantities()
        return redirect(book.get_absolute_url())
