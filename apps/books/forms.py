"""Kitob va nusxalar uchun formalar."""
from django import forms

from apps.books.models import Book, BookCopy

INPUT = {"class": "form-input"}
SELECT = {"class": "form-select"}
AREA = {"class": "form-input", "rows": 3}


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = [
            "title", "author", "category", "isbn", "publisher",
            "publication_year", "room", "shelf", "tier", "description", "cover",
        ]
        widgets = {
            "title": forms.TextInput(attrs={**INPUT, "placeholder": "Kitob nomi"}),
            "author": forms.Select(attrs=SELECT),
            "category": forms.Select(attrs=SELECT),
            "isbn": forms.TextInput(attrs={**INPUT, "placeholder": "978-..."}),
            "publisher": forms.TextInput(attrs=INPUT),
            "publication_year": forms.NumberInput(attrs={**INPUT, "min": 1400, "max": 2100}),
            "room": forms.NumberInput(attrs={**INPUT, "min": 1, "max": 99, "placeholder": "2"}),
            "shelf": forms.TextInput(attrs={**INPUT, "placeholder": "1A"}),
            "tier": forms.NumberInput(attrs={**INPUT, "min": 1, "max": 99, "placeholder": "3"}),
            "description": forms.Textarea(attrs=AREA),
        }
        help_texts = {
            "room": "Kitob turgan xona raqami",
            "shelf": "Qatordagi javon: 1A, 2A ... 1B, 2B",
            "tier": "Javonning nechanchi taxchasi",
        }

    def clean_shelf(self):
        from apps.books.location import normalize_shelf

        raw = (self.cleaned_data.get("shelf") or "").strip()
        if not raw:
            return ""
        shelf = normalize_shelf(raw)
        if not shelf:
            raise forms.ValidationError(
                "Javon raqam va harfdan iborat bo'lsin, masalan: 1A, 2B, 12C."
            )
        return shelf

    def clean_isbn(self):
        isbn = (self.cleaned_data.get("isbn") or "").strip()
        if not isbn:
            return isbn
        digits = isbn.replace("-", "").replace(" ", "")
        if not digits.isdigit() or len(digits) not in (10, 13):
            raise forms.ValidationError("ISBN 10 yoki 13 ta raqamdan iborat bo'lishi kerak.")
        qs = Book.objects.filter(isbn=isbn)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Bu ISBN bilan kitob allaqachon mavjud.")
        return isbn

    def clean_publication_year(self):
        year = self.cleaned_data.get("publication_year")
        if year and year > 2100:
            raise forms.ValidationError("Nashr yili noto'g'ri.")
        return year


class BookCopyForm(forms.ModelForm):
    class Meta:
        model = BookCopy
        fields = ["inventory_number", "status", "shelf_location", "note"]
        widgets = {
            "inventory_number": forms.TextInput(attrs={**INPUT, "placeholder": "INV-0001-001"}),
            "status": forms.Select(attrs=SELECT),
            "shelf_location": forms.TextInput(attrs=INPUT),
            "note": forms.TextInput(attrs=INPUT),
        }


class BookCopyBulkForm(forms.Form):
    """Bir nechta nusxani bir urinishda yaratish."""

    count = forms.IntegerField(
        label="Nusxalar soni", min_value=1, max_value=500, initial=1,
        widget=forms.NumberInput(attrs=INPUT),
    )
    prefix = forms.CharField(
        label="Inventar prefiksi", required=False,
        widget=forms.TextInput(attrs={**INPUT, "placeholder": "INV-0001"}),
    )


class BookBulkImportForm(forms.Form):
    """Excel fayldan ko'plab kitob qo'shish yoki joylashuvni yuklash formasi."""

    MODE_CHOICES = (
        ("yangi", "Yangi kitoblar qo'shish"),
        ("joy", "Mavjud kitoblarga joylashuv yozish (xona, javon, taxcha)"),
    )

    mode = forms.ChoiceField(
        label="Nima qilamiz?", choices=MODE_CHOICES, initial="yangi",
        widget=forms.RadioSelect,
    )
    file = forms.FileField(
        label="Excel fayl (.xlsx)",
        widget=forms.ClearableFileInput(attrs={
            "class": "dropzone-input",
            "accept": ".xlsx,.xlsm",
        }),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        name = (uploaded.name or "").lower()
        if not name.endswith((".xlsx", ".xlsm")):
            raise forms.ValidationError(
                "Faqat Excel fayl (.xlsx) qabul qilinadi."
            )
        if uploaded.size > 15 * 1024 * 1024:
            raise forms.ValidationError(
                "Fayl juda katta (15 MB dan oshmasligi kerak)."
            )
        return uploaded
