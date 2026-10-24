from rest_framework.permissions import BasePermission


class ReaderAccountPermission(BasePermission):
    """Faqat faol, o'z Reader profiliga bog'langan kitobxon akkaunti."""

    message = "Bu amal uchun faol kitobxon akkaunti kerak."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if getattr(user, "role", None) != "reader":
            return False
        try:
            return user.reader_profile.status == "active"
        except Exception:
            return False
