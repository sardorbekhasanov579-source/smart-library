"""Ijtimoiy faollik ballarini qayta hisoblaydi.

    python manage.py recalc_activity

Kitob berish/qaytarish va test natijalaridan ball yozuvlarini yaratadi.
Takroran ishga tushirish xavfsiz — mavjud yozuvlar dublikat qilinmaydi,
sozlamadagi ball qiymati o'zgargan bo'lsa yangilanadi.

Kunlik vazifa bilan birga ishlatish tavsiya etiladi.
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.activity.models import ActivityRecord
from apps.activity.services import recalc_loans, recalc_quizzes


class Command(BaseCommand):
    help = "Ijtimoiy faollik ballarini qayta hisoblaydi"

    def add_arguments(self, parser):
        parser.add_argument(
            "--only", choices=["loans", "quizzes"],
            help="Faqat bitta manbani hisoblash",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Avtomatik yozuvlarni o'chirib, noldan hisoblash "
                 "(qo'lda berilgan ballar saqlanadi)",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            deleted, _ = ActivityRecord.objects.exclude(source_key="").delete()
            self.stdout.write(
                self.style.WARNING(f"{deleted} ta avtomatik yozuv o'chirildi")
            )

        created = 0
        if options["only"] != "quizzes":
            self.stdout.write("Kitob operatsiyalari hisoblanmoqda...")
            created += recalc_loans()
        if options["only"] != "loans":
            self.stdout.write("Test natijalari hisoblanmoqda...")
            created += recalc_quizzes()

        total_records = ActivityRecord.objects.count()
        total_points = ActivityRecord.objects.aggregate(s=Sum("points"))["s"] or 0

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Yangi yozuvlar: {created} ta"))
        self.stdout.write(f"Jami yozuvlar: {total_records} ta")
        self.stdout.write(f"Jami ball: {total_points}")
