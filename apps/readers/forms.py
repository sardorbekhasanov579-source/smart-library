from django import forms

from apps.readers.models import Reader

INPUT = {"class": "form-input"}


class ReaderForm(forms.ModelForm):
    class Meta:
        model = Reader
        fields = [
            "full_name", "reader_code", "phone", "email", "address",
            "reader_type", "registration_date", "status", "note",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={**INPUT, "placeholder": "Abdullayev Aziz"}),
            "reader_code": forms.TextInput(attrs={**INPUT, "placeholder": "KX-000001"}),
            "phone": forms.TextInput(attrs={**INPUT, "placeholder": "+998 90 123 45 67"}),
            "email": forms.EmailInput(attrs=INPUT),
            "address": forms.TextInput(attrs=INPUT),
            "reader_type": forms.Select(attrs={"class": "form-select"}),
            "registration_date": forms.DateInput(attrs={**INPUT, "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "note": forms.Textarea(attrs={**INPUT, "rows": 3}),
        }

    def clean_reader_code(self):
        code = self.cleaned_data["reader_code"].strip().upper()
        qs = Reader.objects.filter(reader_code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Bu kod band. Boshqa kod kiriting.")
        return code

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if phone and len(phone.replace(" ", "").replace("+", "").replace("-", "")) < 7:
            raise forms.ValidationError("Telefon raqam to'liq emas.")
        return phone
