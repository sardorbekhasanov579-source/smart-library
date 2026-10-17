from django import forms
from django.contrib.auth.forms import AuthenticationForm

from apps.users.models import User

INPUT = {"class": "form-input"}
SELECT = {"class": "form-select"}


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Login",
        widget=forms.TextInput(attrs={**INPUT, "placeholder": "Login", "autofocus": True}),
    )
    password = forms.CharField(
        label="Parol",
        widget=forms.PasswordInput(attrs={**INPUT, "placeholder": "Parol"}),
    )
    error_messages = {
        "invalid_login": "Login yoki parol noto'g'ri.",
        "inactive": "Hisobingiz bloklangan. Administratorga murojaat qiling.",
    }


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Parol", widget=forms.PasswordInput(attrs=INPUT), min_length=6
    )
    password2 = forms.CharField(
        label="Parolni takrorlang", widget=forms.PasswordInput(attrs=INPUT)
    )

    class Meta:
        model = User
        fields = ["full_name", "username", "email", "phone", "role", "status"]
        widgets = {
            "full_name": forms.TextInput(attrs=INPUT),
            "username": forms.TextInput(attrs=INPUT),
            "email": forms.EmailInput(attrs=INPUT),
            "phone": forms.TextInput(attrs=INPUT),
            "role": forms.Select(attrs=SELECT),
            "status": forms.Select(attrs=SELECT),
        }

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Bu login band.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Parollar mos kelmadi.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.is_staff = user.role == "admin"
        if commit:
            user.save()
        return user


class AdminPasswordResetForm(forms.Form):
    """Administrator boshqa foydalanuvchiga yangi parol belgilashi uchun."""

    password1 = forms.CharField(
        label="Yangi parol",
        min_length=6,
        widget=forms.TextInput(attrs={**INPUT, "autocomplete": "new-password"}),
        help_text="Kamida 6 ta belgi. Parol ko'rinib turadi — nusxa olib foydalanuvchiga bering.",
    )
    password2 = forms.CharField(
        label="Parolni takrorlang",
        widget=forms.TextInput(attrs={**INPUT, "autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Parollar mos kelmadi.")
        return cleaned


class UserChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "username", "email", "phone", "role", "status"]
        widgets = {
            "full_name": forms.TextInput(attrs=INPUT),
            "username": forms.TextInput(attrs=INPUT),
            "email": forms.EmailInput(attrs=INPUT),
            "phone": forms.TextInput(attrs=INPUT),
            "role": forms.Select(attrs=SELECT),
            "status": forms.Select(attrs=SELECT),
        }

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Bu login band.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = user.role == "admin"
        if commit:
            user.save()
        return user
