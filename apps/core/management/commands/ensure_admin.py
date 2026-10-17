"""Serverda birinchi administratorni yaratadi (agar hali bo'lmasa).

Muhit o'zgaruvchilari orqali ishlaydi — build jarayonida chaqirish uchun qulay:

    ADMIN_USERNAME=admin ADMIN_PASSWORD=... python manage.py ensure_admin

Foydalanuvchi allaqachon mavjud bo'lsa hech narsa o'zgarmaydi, shuning uchun
har bir joylashtirishda xavfsiz ishga tushaveradi.
"""
import os

from django.core.management.base import BaseCommand

from apps.users.models import Role, User, UserStatus


class Command(BaseCommand):
    help = "Birinchi administratorni yaratadi (mavjud bo'lsa tegmaydi)"

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Login (standart: ADMIN_USERNAME)")
        parser.add_argument("--password", help="Parol (standart: ADMIN_PASSWORD)")
        parser.add_argument("--full-name", help="F.I.Sh.")

    def handle(self, *args, **options):
        username = (options["username"] or os.environ.get("ADMIN_USERNAME", "")).strip()
        password = options["password"] or os.environ.get("ADMIN_PASSWORD", "")
        full_name = (
            options["full_name"] or os.environ.get("ADMIN_FULL_NAME", "") or "Administrator"
        )

        if not username or not password:
            self.stdout.write(
                "ADMIN_USERNAME va ADMIN_PASSWORD berilmagan — o'tkazib yuborildi."
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"'{username}' allaqachon mavjud — o'zgartirilmadi.")
            return

        User.objects.create_superuser(
            username=username,
            password=password,
            full_name=full_name,
            role=Role.ADMIN,
            status=UserStatus.ACTIVE,
        )
        self.stdout.write(self.style.SUCCESS(f"Administrator yaratildi: {username}"))
        self.stdout.write(
            self.style.WARNING("Birinchi kirishdan keyin parolni o'zgartiring.")
        )
