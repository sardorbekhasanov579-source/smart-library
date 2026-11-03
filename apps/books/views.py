"""2-modul: Kitoblar - kitoblar va nusxalarni boshqarish."""
import logging

from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView, View,
)

from apps.books import bulk_import
from apps.books.forms import (
    BookBulkImportForm, BookCopyBulkForm, BookCopyForm, BookForm,
)
from apps.books.models import Book, BookCopy, CopyStatus
from apps.catalog.models import Author, Category
from apps.core.mixins import AnyRoleMixin, AuditLogMixin, LibrarianRequiredMixin
from apps.core.models import AuditLog

logger = logging.getLogger(__name__)


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


# ===========================================================================
# Excel orqali ommaviy qo'shish / joylashuv yuklash
# ===========================================================================
class BookBulkImportView(LibrarianRequiredMixin, View):
    """1-bosqich: Excel faylni yuklash va tahlil natijasini ko'rsatish.

    Hech narsa bazaga yozilmaydi - faqat nima bo'lishi ko'rsatiladi,
    kutubxonachi "Tasdiqlash" tugmasini bosgandan keyingina yoziladi.
    """

    template_name = "books/bulk_import.html"

    def get(self, request):
        initial = {"mode": request.GET.get("rejim") or bulk_import.MODE_NEW}
        return render(request, self.template_name, {"form": BookBulkImportForm(initial=initial)})

    def _fail(self, request, token, text, mode):
        bulk_import.discard_temp_file(token)
        messages.error(request, text)
        form = BookBulkImportForm(initial={"mode": mode})
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = BookBulkImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        mode = form.cleaned_data["mode"]
        uploaded = form.cleaned_data["file"]
        token = bulk_import.save_temp_file(uploaded)
        path = bulk_import.temp_file_path(token)

        try:
            if mode == bulk_import.MODE_LOCATION:
                parsed = bulk_import.parse_locations(path)
            else:
                parsed = bulk_import.parse_workbook(path)
        except Exception:
            logger.exception("Excel tahlilida xato")
            return self._fail(
                request, token,
                "Faylni o'qib bo'lmadi. Excel (.xlsx) fayl ekanini tekshiring.", mode,
            )

        if mode == bulk_import.MODE_LOCATION:
            if parsed["missing_key"]:
                return self._fail(
                    request, token,
                    "Kitobni aniqlaydigan ustun topilmadi. Sarlavhada «kitob nomi» "
                    "yoki «inventar» so'zi bo'lishi kerak.", mode,
                )
            if parsed["missing_location"]:
                return self._fail(
                    request, token,
                    "Joylashuv ustuni topilmadi. Sarlavhalarda «xona», «javon» va "
                    "«taxcha» so'zlari bo'lishi kerak.", mode,
                )
            if parsed["total"] == 0:
                return self._fail(request, token, "Faylda to'ldirilgan qator topilmadi.", mode)
            template = "books/bulk_location_preview.html"
        else:
            if parsed["missing_title"]:
                return self._fail(
                    request, token,
                    "Faylda kitob nomi ustuni topilmadi. Ustun sarlavhasida "
                    "\"nomi\" yoki \"kitob\" so'zi bo'lishi kerak.", mode,
                )
            if parsed["total"] == 0:
                return self._fail(request, token, "Faylda to'ldirilgan qator topilmadi.", mode)
            template = "books/bulk_import_preview.html"

        return render(
            request, template,
            {"token": token, "result": parsed, "filename": uploaded.name, "mode": mode},
        )


class BookBulkImportConfirmView(LibrarianRequiredMixin, View):
    """2-bosqich: tasdiqlangandan keyin haqiqiy yozish."""

    def post(self, request, token):
        mode = request.POST.get("mode") or bulk_import.MODE_NEW
        path = bulk_import.temp_file_path(token)
        if not path:
            messages.error(
                request,
                "Fayl muddati tugagan yoki topilmadi. Qaytadan yuklang.",
            )
            return redirect("books:bulk_import")

        try:
            if mode == bulk_import.MODE_LOCATION:
                parsed = bulk_import.parse_locations(path)
                report = bulk_import.commit_locations(parsed["rows"], user=request.user)
            else:
                parsed = bulk_import.parse_workbook(path)
                report = bulk_import.commit_rows(parsed["rows"], user=request.user)
        except Exception:
            logger.exception("Excel yozishda xato")
            messages.error(
                request,
                "Yozishda xatolik yuz berdi. Faylni tekshirib qaytadan urinib ko'ring.",
            )
            return redirect("books:bulk_import")
        finally:
            bulk_import.discard_temp_file(token)

        if mode == bulk_import.MODE_LOCATION:
            messages.success(
                request,
                f"Tayyor! {report['books']} ta kitobga joylashuv yozildi"
                + (f", {report['copies']} ta nusxaga alohida" if report["copies"] else "")
                + ".",
            )
            return redirect("books:shelf_map")

        messages.success(
            request,
            (
                f"Tayyor! {report['created_books']} ta yangi kitob qo'shildi, "
                f"{report['reused_books']} ta mavjud kitobga nusxa qo'shildi, "
                f"jami {report['created_copies']} ta nusxa yaratildi."
            ),
        )
        return redirect(reverse("books:list"))


# ===========================================================================
# Javonlar xaritasi: Xona -> qator -> javon -> taxcha
# ===========================================================================
class ShelfMapView(AnyRoleMixin, View):
    """Har bir xonadagi javonlar va ulardagi kitoblar soni."""

    template_name = "books/shelf_map.html"

    def get(self, request):
        from apps.books.location import shelf_sort_key
        from apps.core.models import SystemSetting

        rows = (
            Book.objects.exclude(shelf="")
            .values("room", "shelf")
            .annotate(n=Count("id"))
        )
        rooms = {}
        for item in rows:
            room = item["room"] or 0
            shelf = item["shelf"]
            letter = shelf[-1:]
            rooms.setdefault(room, {}).setdefault(letter, []).append(
                {"shelf": shelf, "n": item["n"]}
            )

        room_count = SystemSetting.get_int("library_rooms", 3)
        for number in range(1, room_count + 1):
            rooms.setdefault(number, {})

        room_list = []
        for number in sorted(rooms, key=lambda r: (r == 0, r)):
            letters = []
            for letter in sorted(rooms[number]):
                shelves = sorted(rooms[number][letter], key=lambda s: shelf_sort_key(s["shelf"]))
                letters.append({"letter": letter, "shelves": shelves})
            room_list.append({
                "number": number,
                "letters": letters,
                "books": sum(s["n"] for l in letters for s in l["shelves"]),
                "shelves": sum(len(l["shelves"]) for l in letters),
            })

        total = Book.objects.count()
        placed = Book.objects.exclude(shelf="").count()
        return render(request, self.template_name, {
            "rooms": room_list,
            "total": total,
            "placed": placed,
            "unplaced": total - placed,
            "percent": round(placed * 100 / total) if total else 0,
        })


class ShelfDetailView(AnyRoleMixin, View):
    """Bitta javon: taxchalar bo'yicha kitoblar."""

    template_name = "books/shelf_detail.html"

    def get(self, request, room, shelf):
        from apps.books.location import normalize_shelf

        shelf = normalize_shelf(shelf)
        if not shelf:
            raise Http404("Javon topilmadi")
        books = Book.objects.select_related("author", "category").filter(shelf=shelf)
        books = books.filter(room__isnull=True) if room == 0 else books.filter(room=room)
        tiers = {}
        for book in books.order_by("tier", "title"):
            tiers.setdefault(book.tier or 0, []).append(book)
        return render(request, self.template_name, {
            "room": room,
            "shelf": shelf,
            "tiers": sorted(tiers.items(), key=lambda kv: (kv[0] == 0, kv[0])),
            "count": sum(len(v) for v in tiers.values()),
        })
