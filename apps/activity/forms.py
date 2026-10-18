"""Ijtimoiy faollik formalari."""
from django import forms
from django.utils import timezone

from apps.readers.models import Reader, ReaderStatus

INPUT = {"class": "form-input"}
SELECT = {"class": "form-select"}


class ManualAwardForm(forms.Form):
    """Kutubxonachi qo'lda ball berishi (tadbir, kitob sovg'asi va h.k.)."""

    reader = forms.ModelChoiceField(
        label="Kitobxon",
        queryset=Reader.objects.none(),
        widget=forms.Select(attrs=SELECT),
    )
    points = forms.IntegerField(
        label="Ball",
        min_value=-100,
        max_value=100,
        widget=forms.NumberInput(attrs=INPUT),
        help_text="Manfiy son ham kiritish mumkin (jarima bali).",
    )
    happened_at = forms.DateField(
        label="Sana",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={**INPUT, "type": "date"}),
    )
    note = forms.CharField(
        label="Izoh",
        max_length=255,
        widget=forms.TextInput(
            attrs={**INPUT, "placeholder": "Masalan: kitobxonlar kechasida ishtirok etdi"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reader"].queryset = (
            Reader.objects.exclude(status=ReaderStatus.ARCHIVED)
            .order_by("full_name")
        )
        self.fields["reader"].label_from_instance = (
            lambda obj: f"{obj.full_name} ({obj.reader_code})"
        )


class PeriodForm(forms.Form):
    """Reyting uchun davr tanlash."""

    date_from = forms.DateField(
        label="Sanadan",
        required=False,
        widget=forms.DateInput(attrs={**INPUT, "type": "date"}),
    )
    date_to = forms.DateField(
        label="Sanagacha",
        required=False,
        widget=forms.DateInput(attrs={**INPUT, "type": "date"}),
    )
