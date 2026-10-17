"""Testlar moduli formalari."""
from django import forms
from django.utils import timezone

from apps.loans.models import Loan
from apps.quizzes.models import Choice, Question


class BootstrapMixin:
    """Barcha maydonlarga loyiha CSS klasslarini qo'shadi."""

    def _style(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.CheckboxInput):
                continue
            else:
                widget.attrs.setdefault("class", "form-input")


class QuestionForm(BootstrapMixin, forms.Form):
    """Savolni 4 ta variant bilan qo'lda kiritish / tahrirlash."""

    text = forms.CharField(
        label="Savol matni",
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    choice_1 = forms.CharField(label="1-variant", max_length=500)
    choice_2 = forms.CharField(label="2-variant", max_length=500)
    choice_3 = forms.CharField(label="3-variant", max_length=500, required=False)
    choice_4 = forms.CharField(label="4-variant", max_length=500, required=False)
    correct = forms.ChoiceField(
        label="To'g'ri javob",
        choices=[("1", "1-variant"), ("2", "2-variant"), ("3", "3-variant"), ("4", "4-variant")],
        initial="1",
    )
    explanation = forms.CharField(
        label="Izoh (ixtiyoriy)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance and not self.is_bound:
            choices = list(instance.choices.all())
            initial = {"text": instance.text, "explanation": instance.explanation}
            for index, choice in enumerate(choices[:4], start=1):
                initial[f"choice_{index}"] = choice.text
                if choice.is_correct:
                    initial["correct"] = str(index)
            self.initial.update(initial)
        self._style()

    def clean(self):
        data = super().clean()
        values = [data.get(f"choice_{i}", "").strip() for i in range(1, 5)]
        filled = [v for v in values if v]
        if len(filled) < 2:
            raise forms.ValidationError("Kamida 2 ta variant kiritilishi kerak.")
        correct = data.get("correct") or "1"
        if not values[int(correct) - 1]:
            raise forms.ValidationError("To'g'ri javob sifatida bo'sh variant tanlangan.")
        if len(set(filled)) != len(filled):
            raise forms.ValidationError("Variantlar bir xil bo'lmasligi kerak.")
        data["_values"] = values
        return data

    def save(self, quiz):
        """Savolni (va variantlarini) saqlaydi."""
        values = self.cleaned_data["_values"]
        correct_index = int(self.cleaned_data["correct"]) - 1

        question = self.instance
        if question is None:
            last = quiz.questions.order_by("-order").first()
            question = Question(quiz=quiz, order=(last.order + 1) if last else 1)
        question.text = self.cleaned_data["text"].strip()
        question.explanation = self.cleaned_data.get("explanation", "").strip()
        question.save()

        question.choices.all().delete()
        Choice.objects.bulk_create(
            [
                Choice(
                    question=question,
                    text=value,
                    is_correct=(position == correct_index),
                    order=position + 1,
                )
                for position, value in enumerate(values)
                if value
            ]
        )
        return question


class AssignmentCreateForm(BootstrapMixin, forms.Form):
    """Kutubxonachi testni qo'lda biriktirishi uchun."""

    loan = forms.ModelChoiceField(
        label="Operatsiya (kitobxon + kitob)",
        queryset=Loan.objects.none(),
        help_text="Faqat qaytarilmagan kitoblar ko'rsatiladi.",
    )
    question_count = forms.IntegerField(
        label="Savollar soni", min_value=1, max_value=100, required=False
    )
    pass_percent = forms.IntegerField(
        label="O'tish chegarasi (%)", min_value=1, max_value=100, required=False
    )
    send_now = forms.BooleanField(
        label="Darhol Telegram orqali yuborish", required=False, initial=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["loan"].queryset = (
            Loan.objects.select_related("reader", "copy__book")
            .filter(return_date__isnull=True)
            .order_by("due_date")
        )
        self.fields["loan"].label_from_instance = (
            lambda obj: f"{obj.reader.full_name} — {obj.copy.book.title} "
                        f"(muddat {obj.due_date:%d.%m.%Y})"
        )
        self._style()


class PhoneForm(BootstrapMixin, forms.Form):
    """Kabinetga kirish: telefon raqam."""

    phone = forms.CharField(
        label="Telefon raqamingiz",
        max_length=32,
        widget=forms.TextInput(attrs={"placeholder": "+998 90 123 45 67", "inputmode": "tel"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class CodeForm(BootstrapMixin, forms.Form):
    """Kabinetga kirish: Telegramdan kelgan kod."""

    code = forms.CharField(
        label="Telegramdan kelgan kod",
        max_length=8,
        widget=forms.TextInput(
            attrs={"placeholder": "6 xonali kod", "inputmode": "numeric", "autocomplete": "off"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class QuizSettingsForm(BootstrapMixin, forms.Form):
    """Test to'plamining sozlamalari."""

    title = forms.CharField(label="Test nomi", max_length=255, required=False)
    question_target = forms.IntegerField(label="Savollar soni (maqsad)", min_value=1, max_value=100)
    pass_percent = forms.IntegerField(label="O'tish chegarasi (%)", min_value=1, max_value=100)
    is_active = forms.BooleanField(label="Faol", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class TestMessageForm(BootstrapMixin, forms.Form):
    """Telegram sozlamalarini tekshirish uchun sinov xabari."""

    chat_id = forms.CharField(label="Chat ID", max_length=32)
    text = forms.CharField(
        label="Xabar matni",
        initial="Salom! Bu kutubxona botidan sinov xabari.",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


def today_label():
    return timezone.localdate().strftime("%d.%m.%Y")
