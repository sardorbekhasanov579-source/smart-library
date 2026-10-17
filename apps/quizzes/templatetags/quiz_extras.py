"""Testlar moduli shablonlari uchun filtrlar."""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

_ASSIGNMENT_CLASSES = {
    "pending": "badge-gray",
    "sent": "badge-blue",
    "started": "badge-amber",
    "passed": "badge-green",
    "failed": "badge-red",
    "expired": "badge-red",
}


@register.filter
def assignment_badge(assignment):
    """Topshiriq holatini rangli nishon qilib chiqaradi."""
    code = getattr(assignment, "status", "")
    label = (
        assignment.get_status_display()
        if hasattr(assignment, "get_status_display")
        else str(code)
    )
    css = _ASSIGNMENT_CLASSES.get(str(code), "badge-gray")
    return mark_safe(f'<span class="badge {css}">{label}</span>')


@register.filter
def percent_badge(value):
    """Foiz natijani rangli nishon qilib chiqaradi."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return mark_safe('<span class="muted">—</span>')
    if number >= 70:
        css = "badge-green"
    elif number >= 40:
        css = "badge-amber"
    else:
        css = "badge-red"
    return mark_safe(f'<span class="badge {css}">{number}%</span>')


@register.filter
def answer_for(answers, question):
    """Javoblar ro'yxatidan ushbu savolga tegishlisini topadi."""
    question_id = getattr(question, "pk", question)
    for answer in answers:
        if answer.question_id == question_id:
            return answer
    return None
