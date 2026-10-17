"""Tizim foydalanuvchilari va rollar (users jadvali)."""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    ADMIN = "admin", "Administrator"
    LIBRARIAN = "librarian", "Kutubxonachi"
    READER = "reader", "Kitobxon"


class UserStatus(models.TextChoices):
    ACTIVE = "active", "Faol"
    BLOCKED = "blocked", "Bloklangan"


class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Login (username) kiritilishi shart")
        extra_fields.setdefault("role", Role.LIBRARIAN)
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.ADMIN)
        extra_fields.setdefault("status", UserStatus.ACTIVE)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser uchun is_staff=True bo'lishi kerak")
        return self.create_user(username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """ER: users (id, full_name, username, password_hash, role, status, created_at)."""

    full_name = models.CharField("F.I.Sh.", max_length=150)
    username = models.CharField("Login", max_length=64, unique=True)
    email = models.EmailField("Email", blank=True)
    phone = models.CharField("Telefon", max_length=32, blank=True)
    role = models.CharField("Rol", max_length=16, choices=Role.choices, default=Role.LIBRARIAN)
    status = models.CharField(
        "Holat", max_length=16, choices=UserStatus.choices, default=UserStatus.ACTIVE
    )
    created_at = models.DateTimeField("Yaratilgan", default=timezone.now)

    is_staff = models.BooleanField("Admin panelga kirish", default=False)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"

    @property
    def is_active(self):
        # Django autentifikatsiyasi shu xususiyatdan foydalanadi.
        return self.status == UserStatus.ACTIVE

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_librarian(self):
        return self.role == Role.LIBRARIAN

    @property
    def is_reader(self):
        return self.role == Role.READER

    def can_manage_library(self):
        """Kitob berish/qaytarish, kitob va kitobxonlarni boshqarish huquqi."""
        return self.role in {Role.ADMIN, Role.LIBRARIAN}

    def initials(self):
        parts = [p for p in self.full_name.split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or self.username[:2].upper()
