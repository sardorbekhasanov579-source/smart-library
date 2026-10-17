"""Rollarga asoslangan kirish nazorati (3-bo'lim: foydalanuvchi rollari)."""
from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect

from apps.users.models import Role


class RoleRequiredMixin(AccessMixin):
    """Faqat ruxsat etilgan rollarga sahifani ochadi."""

    allowed_roles = (Role.ADMIN, Role.LIBRARIAN)
    permission_message = "Bu bo'limga kirish huquqingiz yo'q."

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role not in self.allowed_roles:
            messages.error(request, self.permission_message)
            return redirect("core:dashboard")
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    """Faqat administrator."""

    allowed_roles = (Role.ADMIN,)
    permission_message = "Bu amal faqat administrator uchun."


class LibrarianRequiredMixin(RoleRequiredMixin):
    """Administrator yoki kutubxonachi."""

    allowed_roles = (Role.ADMIN, Role.LIBRARIAN)


class AnyRoleMixin(RoleRequiredMixin):
    """Tizimga kirgan har qanday foydalanuvchi (kitobxon ham)."""

    allowed_roles = (Role.ADMIN, Role.LIBRARIAN, Role.READER)


class AuditLogMixin:
    """CreateView/UpdateView/DeleteView uchun amallarni jurnalga yozadi."""

    audit_entity = ""

    def _log(self, action, obj, details=""):
        from apps.core.models import AuditLog

        AuditLog.log(
            user=self.request.user,
            action=action,
            entity_type=self.audit_entity or obj.__class__.__name__.lower(),
            entity_id=getattr(obj, "pk", None),
            details=details or str(obj),
        )

    def form_valid(self, form):
        from apps.core.models import AuditLog

        is_new = form.instance.pk is None
        response = super().form_valid(form)
        self._log(
            AuditLog.Action.CREATE if is_new else AuditLog.Action.UPDATE,
            self.object,
        )
        return response
