"""Barcha shablonlarga umumiy ma'lumot uzatish."""
from django.utils import timezone


def site_settings(request):
    from apps.core.models import SystemSetting

    user = getattr(request, "user", None)
    ctx = {
        "LIBRARY_NAME": SystemSetting.library_name(),
        "TODAY": timezone.localdate(),
    }
    if user is not None and user.is_authenticated:
        ctx["can_manage"] = user.can_manage_library()
        ctx["is_admin_role"] = user.is_admin
    else:
        ctx["can_manage"] = False
        ctx["is_admin_role"] = False
    return ctx
