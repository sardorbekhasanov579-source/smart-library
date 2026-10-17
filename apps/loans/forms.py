"""Kitob berish va qaytarish formalari."""
from django import forms

from apps.books.models import BookCopy, CopyStatus
from apps.core.models import SystemSetting
from apps.readers.models import Reader, ReaderStatus

INPUT = {"class": "form-input"}
SELECT = {"class": "form-select"}


class IssueForm(forms.Form):
    """Kitob berish: kitobxon + mavjud nusxa + muddat."""

    reader = forms.ModelChoiceField(
        label="Kitobxon",
        queryset=Reader.objects.filter(status=ReaderStatus.ACTIVE),
        widget=forms.Select(attrs={**SELECT, "data-searchable": "1"}),
        empty_label="— Kitobxonni tanlang —",
    )
    copy = forms.ModelChoiceField(
        label="Kitob nusxasi",
        queryset=BookCopy.objects.filter(status=CopyStatus.AVAILABLE).select_related("book"),
        widget=forms.Select(attrs={**SELECT, "data-searchable": "1"}),
        empty_label="— Nusxani tanlang —",
    )
    days = forms.IntegerField(
        label="Muddat (kun)", min_value=1, max_value=365,
        widget=forms.NumberInput(attrs=INPUT),
    )
    note = forms.CharField(
        label="Izoh", required=False, widget=forms.TextInput(attrs=INPUT)
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["days"].initial = SystemSetting.loan_days()
        self.fields["copy"].label_from_instance = (
            lambda obj: f"{obj.book.title} — {obj.inventory_number}"
        )
        self.fields["reader"].label_from_instance = (
            lambda obj: f"{obj.full_name} ({obj.reader_code})"
        )

    def clean_copy(self):
        copy = self.cleaned_data["copy"]
        if copy.status != CopyStatus.AVAILABLE:
            raise forms.ValidationError("Bu nusxa hozir mavjud emas.")
        return copy

    def clean_reader(self):
        reader = self.cleaned_data["reader"]
        if not reader.can_borrow:
            limit = SystemSetting.max_books_per_reader()
            if reader.overdue_loans_count:
                raise forms.ValidationError(
                    "Kitobxonda muddati o'tgan kitob bor - avval qaytarsin."
                )
            raise forms.ValidationError(
                f"Kitobxon limitga yetgan (maksimum {limit} ta kitob)."
            )
        return reader


class ReturnForm(forms.Form):
    """Qaytarib olish: nusxaning qaytgandagi holati."""

    CONDITION_CHOICES = [
        (CopyStatus.AVAILABLE, "Yaxshi holatda"),
        (CopyStatus.DAMAGED, "Shikastlangan"),
        (CopyStatus.LOST, "Yo'qolgan"),
    ]

    condition = forms.ChoiceField(
        label="Nusxa holati", choices=CONDITION_CHOICES,
        initial=CopyStatus.AVAILABLE, widget=forms.Select(attrs=SELECT),
    )
    note = forms.CharField(
        label="Izoh", required=False, widget=forms.TextInput(attrs=INPUT)
    )
