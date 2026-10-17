from django import forms

from apps.catalog.models import Author, Category

INPUT = {"class": "form-input"}


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ["full_name", "birth_year", "description"]
        widgets = {
            "full_name": forms.TextInput(attrs={**INPUT, "placeholder": "Abdulla Qodiriy"}),
            "birth_year": forms.NumberInput(attrs={**INPUT, "min": 1, "max": 2100}),
            "description": forms.Textarea(attrs={**INPUT, "rows": 4}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "description"]
        widgets = {
            "name": forms.TextInput(attrs={**INPUT, "placeholder": "Badiiy adabiyot"}),
            "parent": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={**INPUT, "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # O'zini yoki o'z avlodini "ota toifa" qilib tanlashni taqiqlash
            excluded = self.instance.all_descendant_ids()
            self.fields["parent"].queryset = Category.objects.exclude(pk__in=excluded)
        self.fields["parent"].empty_label = "— Ildiz toifa —"

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get("parent")
        if parent and self.instance.pk and parent.pk in self.instance.all_descendant_ids():
            raise forms.ValidationError("Toifa o'z ichki toifasiga bo'ysuna olmaydi.")
        return cleaned
