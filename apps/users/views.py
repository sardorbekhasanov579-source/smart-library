"""9-modul: Foydalanuvchilar - rollar va huquqlar, kirish/chiqish."""
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.db.models import Q
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from apps.core.mixins import AdminRequiredMixin
from apps.core.models import AuditLog
from apps.users.forms import (
    AdminPasswordResetForm,
    LoginForm,
    UserChangeForm,
    UserCreateForm,
)
from apps.users.models import Role, User, UserStatus


class LoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLog.log(
            user=self.request.user,
            action=AuditLog.Action.LOGIN,
            entity_type="user",
            entity_id=self.request.user.pk,
            details=f"{self.request.user.full_name} tizimga kirdi",
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Login yoki parol noto'g'ri.")
        return super().form_invalid(form)


class LogoutView(auth_views.LogoutView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            AuditLog.log(
                user=request.user,
                action=AuditLog.Action.LOGOUT,
                entity_type="user",
                entity_id=request.user.pk,
                details=f"{request.user.full_name} tizimdan chiqdi",
            )
        return super().dispatch(request, *args, **kwargs)


class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "users/user_list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.all()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(username__icontains=q))
        role = self.request.GET.get("role")
        if role:
            qs = qs.filter(role=role)
        return qs.order_by("full_name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["roles"] = Role.choices
        ctx["filters"] = self.request.GET
        return ctx


class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy("users:list")

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLog.log(user=self.request.user, action=AuditLog.Action.CREATE,
                     entity_type="user", entity_id=self.object.pk,
                     details=f"Yangi foydalanuvchi: {self.object.full_name} "
                             f"({self.object.get_role_display()})")
        messages.success(self.request, f"{self.object.full_name} qo'shildi.")
        return response


class UserUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserChangeForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy("users:list")

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLog.log(user=self.request.user, action=AuditLog.Action.UPDATE,
                     entity_type="user", entity_id=self.object.pk,
                     details=f"Foydalanuvchi yangilandi: {self.object.full_name}")
        messages.success(self.request, "Ma'lumotlar yangilandi.")
        return response


class UserDeleteView(AdminRequiredMixin, DeleteView):
    model = User
    template_name = "users/user_confirm_delete.html"
    success_url = reverse_lazy("users:list")

    def form_valid(self, form):
        user = self.get_object()
        if user.pk == self.request.user.pk:
            messages.error(self.request, "O'zingizni o'chira olmaysiz.")
            return redirect("users:list")
        if user.is_admin and User.objects.filter(role=Role.ADMIN).count() <= 1:
            messages.error(self.request, "Tizimda kamida bitta administrator qolishi kerak.")
            return redirect("users:list")
        AuditLog.log(user=self.request.user, action=AuditLog.Action.DELETE,
                     entity_type="user", entity_id=user.pk, details=str(user))
        messages.success(self.request, f"{user.full_name} o'chirildi.")
        return super().form_valid(form)


class UserToggleStatusView(AdminRequiredMixin, View):
    """Foydalanuvchini bloklash / faollashtirish."""

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user.pk == request.user.pk:
            messages.error(request, "O'zingizni bloklay olmaysiz.")
            return redirect("users:list")
        user.status = (
            UserStatus.BLOCKED if user.status == UserStatus.ACTIVE else UserStatus.ACTIVE
        )
        user.save(update_fields=["status"])
        messages.success(request, f"{user.full_name}: {user.get_status_display()}")
        return redirect("users:list")


class UserPasswordResetView(AdminRequiredMixin, View):
    """Administrator foydalanuvchiga yangi parol belgilaydi.

    Kutubxonachi parolini unutsa shu sahifadan tiklanadi — eski parolni
    bilish shart emas.
    """

    template_name = "users/password_reset.html"

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        return render(
            request,
            self.template_name,
            {"target": target, "form": AdminPasswordResetForm()},
        )

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = AdminPasswordResetForm(request.POST)
        if not form.is_valid():
            return render(
                request, self.template_name, {"target": target, "form": form}
            )

        password = form.cleaned_data["password1"]
        target.set_password(password)
        target.save(update_fields=["password"])

        # O'z parolini o'zgartirgan bo'lsa, seansdan chiqib ketmasin
        if target.pk == request.user.pk:
            update_session_auth_hash(request, target)

        AuditLog.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            entity_type="user",
            entity_id=target.pk,
            details=f"{target.full_name} uchun parol tiklandi",
        )
        messages.success(
            request,
            f"{target.full_name} uchun yangi parol o'rnatildi: {password} — "
            "nusxa olib foydalanuvchiga bering.",
        )
        return redirect("users:list")


class ProfileView(UpdateView):
    """Har bir foydalanuvchi o'z profilini tahrirlashi."""

    model = User
    form_class = UserChangeForm
    template_name = "users/profile.html"
    success_url = reverse_lazy("users:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Oddiy foydalanuvchi o'z rolini va holatini o'zgartira olmaydi
        if not self.request.user.is_admin:
            for field in ("role", "status"):
                if field in form.fields:
                    form.fields[field].disabled = True
        return form

    def form_valid(self, form):
        messages.success(self.request, "Profil yangilandi.")
        return super().form_valid(form)


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "users/password_change.html"
    success_url = reverse_lazy("users:profile")

    def form_valid(self, form):
        messages.success(self.request, "Parol muvaffaqiyatli o'zgartirildi.")
        return super().form_valid(form)
