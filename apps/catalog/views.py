"""7-modul: Katalog - toifalar va mualliflar."""
from django.contrib import messages
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.catalog.forms import AuthorForm, CategoryForm
from apps.catalog.models import Author, Category
from apps.core.mixins import AnyRoleMixin, AuditLogMixin, LibrarianRequiredMixin
from apps.core.models import AuditLog


class CatalogHomeView(AnyRoleMixin, ListView):
    """Toifalar daraxti va mualliflar ro'yxati bir sahifada."""

    model = Category
    template_name = "catalog/catalog_home.html"
    context_object_name = "categories"

    def get_queryset(self):
        return (
            Category.objects.select_related("parent")
            .annotate(books_total=Count("books"))
            .order_by("parent__name", "name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        roots = [c for c in ctx["categories"] if c.parent_id is None]
        children = {}
        for c in ctx["categories"]:
            if c.parent_id:
                children.setdefault(c.parent_id, []).append(c)
        ctx["tree"] = [{"node": r, "children": children.get(r.pk, [])} for r in roots]
        ctx["authors"] = Author.objects.annotate(books_total=Count("books")).order_by("full_name")
        return ctx


# --- Toifalar -------------------------------------------------------------
class CategoryCreateView(LibrarianRequiredMixin, AuditLogMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("catalog:home")
    audit_entity = "category"


class CategoryUpdateView(LibrarianRequiredMixin, AuditLogMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("catalog:home")
    audit_entity = "category"


class CategoryDeleteView(LibrarianRequiredMixin, DeleteView):
    model = Category
    template_name = "catalog/confirm_delete.html"
    success_url = reverse_lazy("catalog:home")

    def form_valid(self, form):
        obj = self.get_object()
        if obj.books.exists():
            messages.error(self.request, "Toifada kitoblar bor - avval ularni ko'chiring.")
            return self.render_to_response(self.get_context_data())
        AuditLog.log(user=self.request.user, action=AuditLog.Action.DELETE,
                     entity_type="category", entity_id=obj.pk, details=str(obj))
        messages.success(self.request, "Toifa o'chirildi.")
        return super().form_valid(form)


class CategoryDetailView(AnyRoleMixin, DetailView):
    model = Category
    template_name = "catalog/category_detail.html"
    context_object_name = "category"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["books"] = (
            self.object.books.model.objects.select_related("author")
            .filter(category_id__in=self.object.all_descendant_ids())
            .order_by("title")[:100]
        )
        return ctx


# --- Mualliflar -----------------------------------------------------------
class AuthorListView(AnyRoleMixin, ListView):
    model = Author
    template_name = "catalog/author_list.html"
    context_object_name = "authors"
    paginate_by = 30

    def get_queryset(self):
        qs = Author.objects.annotate(books_total=Count("books"))
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(description__icontains=q))
        return qs.order_by("full_name")


class AuthorDetailView(AnyRoleMixin, DetailView):
    model = Author
    template_name = "catalog/author_detail.html"
    context_object_name = "author"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["books"] = self.object.books.select_related("category").order_by("title")
        return ctx


class AuthorCreateView(LibrarianRequiredMixin, AuditLogMixin, CreateView):
    model = Author
    form_class = AuthorForm
    template_name = "catalog/author_form.html"
    success_url = reverse_lazy("catalog:author_list")
    audit_entity = "author"


class AuthorUpdateView(LibrarianRequiredMixin, AuditLogMixin, UpdateView):
    model = Author
    form_class = AuthorForm
    template_name = "catalog/author_form.html"
    success_url = reverse_lazy("catalog:author_list")
    audit_entity = "author"


class AuthorDeleteView(LibrarianRequiredMixin, DeleteView):
    model = Author
    template_name = "catalog/confirm_delete.html"
    success_url = reverse_lazy("catalog:author_list")

    def form_valid(self, form):
        obj = self.get_object()
        if obj.books.exists():
            messages.error(self.request, "Bu muallifning kitoblari bor - o'chirib bo'lmaydi.")
            return self.render_to_response(self.get_context_data())
        AuditLog.log(user=self.request.user, action=AuditLog.Action.DELETE,
                     entity_type="author", entity_id=obj.pk, details=str(obj))
        messages.success(self.request, "Muallif o'chirildi.")
        return super().form_valid(form)
