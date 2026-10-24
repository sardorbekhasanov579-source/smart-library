"""Shablonlar uchun qo'shimcha filtr va teglar."""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

_STATUS_CLASSES = {
    "available": "badge-green",
    "issued": "badge-blue",
    "returned": "badge-green",
    "overdue": "badge-red",
    "lost": "badge-red",
    "damaged": "badge-amber",
    "written_off": "badge-gray",
    "active": "badge-green",
    "blocked": "badge-red",
    "archived": "badge-gray",
    "waiting": "badge-amber",
    "ready": "badge-blue",
    "done": "badge-green",
    "cancelled": "badge-gray",
}


@register.filter
def status_badge(obj):
    """Model obyekti yoki (kod, matn) juftligi uchun rangli nishon chiqaradi."""
    if hasattr(obj, "effective_status"):
        code = obj.effective_status()
        label = dict(obj._meta.get_field("status").choices).get(code, code)
    elif hasattr(obj, "status"):
        code = obj.status
        label = obj.get_status_display()
    else:
        code = str(obj)
        label = str(obj)
    css = _STATUS_CLASSES.get(str(code), "badge-gray")
    return mark_safe(f'<span class="badge {css}">{label}</span>')


@register.filter
def spaced(value):
    """12500 -> 12 500."""
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return value


@register.filter
def initials(name):
    parts = [p for p in str(name).split() if p]
    return "".join(p[0].upper() for p in parts[:2])


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """Joriy GET parametrlarini saqlab, bir nechtasini almashtiradi (sahifalash uchun)."""
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.filter
def getitem(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def pretty_phone(value):
    """Telefon raqamni o'qishga qulay ko'rinishga keltiradi.

    998901234567 -> +998 90 123 45 67
    """
    from apps.quizzes.utils import pretty_phone as _pretty

    if not value:
        return ""
    try:
        return _pretty(value)
    except Exception:
        return value
