"""Muddati yaqinlashgan kitoblar bo'yicha testlarni yuborish va natijalarni yopish.

Bu komanda kuniga bir marta ishga tushirilishi kerak (Windows Task Scheduler
yoki Linux cron orqali):

    python manage.py send_due_quizzes

Nima qiladi:
  1-qadam. Qaytarish muddatiga N kun qolgan (standart 1 kun), hali qaytarilmagan
           kitoblarni topadi. Har biri uchun test to'plamini oladi (kerak bo'lsa
           AI orqali yaratadi), kitobxonga topshiriq biriktiradi va Telegram
           orqali havolani yuboradi.
  2-qadam. Muddati o'tib ketgan, lekin ishlanmagan topshiriqlarni yopadi va
           adminga "kitobni o'qimagan" xabarini yuboradi.

Qo'shimcha kalitlar:
    --days 2        muddatdan necha kun oldin yuborilsin
    --dry-run       hech narsa saqlanmaydi, faqat ko'rsatadi
    --no-expire     2-qadamni o'tkazib yuboradi
    --loan-id 15    faqat bitta operatsiya uchun (sinov uchun qulay)
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import SystemSetting
from apps.loans.models import Loan
from apps.quizzes.models import Assignment, AssignmentStatus
from apps.quizzes.services import (
    expire_overdue_assignments,
    get_or_create_quiz,
    reader_chat_id,
    send_assignment,
)


class Command(BaseCommand):
    help = "Muddati yaqinlashgan kitoblar bo'yicha testlarni yuboradi"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, help="Muddatdan necha kun oldin (standart: 1)")
        parser.add_argument("--loan-id", type=int, help="Faqat shu operatsiya uchun")
        parser.add_argument("--dry-run", action="store_true", help="Saqlamasdan ko'rsatish")
        parser.add_argument("--no-expire", action="store_true", help="Muddati o'tganlarni yopmaslik")
        parser.add_argument(
            "--resend", action="store_true",
            help="Topshiriq allaqachon bor bo'lsa ham qayta yuborish",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = SystemSetting.quiz_days_before_due()
        dry = options["dry_run"]

        self.stdout.write(self.style.MIGRATE_HEADING("1-qadam: testlarni yuborish"))
        loans = self.collect_loans(days, options["loan_id"])
        if not loans:
            self.stdout.write("  Mos operatsiya topilmadi.")
        sent = skipped = failed = 0

        for loan in loans:
            reader = loan.reader
            book = loan.copy.book
            label = f"{reader.full_name} / {book.title}"

            existing = loan.quiz_assignments.exclude(
                status=AssignmentStatus.EXPIRED
            ).first()
            if existing and not options["resend"]:
                skipped += 1
                self.stdout.write(f"  — {label}: topshiriq allaqachon bor "
                                  f"({existing.get_status_display()})")
                continue

            if not reader_chat_id(reader):
                failed += 1
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ {label}: Telegram ulanmagan, yuborilmadi")
                )
                if not dry:
                    self.ensure_assignment(loan, note="Telegram ulanmagan")
                continue

            if dry:
                self.stdout.write(f"  [dry-run] {label}: test yuborilar edi")
                sent += 1
                continue

            assignment = self.ensure_assignment(loan)
            if not assignment:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f"  ✗ {label}: test to'plami tuzilmadi")
                )
                continue

            ok, message = send_assignment(assignment)
            if ok:
                sent += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ {label}: yuborildi"))
            else:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  ✗ {label}: {message}"))

        self.stdout.write(f"  Natija: yuborildi {sent}, o'tkazildi {skipped}, xato {failed}")

        if not options["no_expire"]:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("2-qadam: muddati o'tganlar"))
            if dry:
                count = Assignment.objects.filter(
                    deadline__lt=timezone.now(),
                    status__in=[AssignmentStatus.PENDING, AssignmentStatus.SENT,
                                AssignmentStatus.STARTED],
                ).count()
                self.stdout.write(f"  [dry-run] {count} ta topshiriq yopilar edi")
            else:
                closed = expire_overdue_assignments()
                self.stdout.write(f"  {closed} ta topshiriq yopildi, adminga xabar berildi")

    # -- yordamchilar --------------------------------------------------------
    def collect_loans(self, days, loan_id=None):
        queryset = Loan.objects.select_related(
            "reader", "copy__book__author", "copy__book__category"
        ).filter(return_date__isnull=True)

        if loan_id:
            return list(queryset.filter(pk=loan_id))

        target = timezone.localdate() + timedelta(days=days)
        return list(queryset.filter(due_date=target).order_by("reader__full_name"))

    def ensure_assignment(self, loan, note=""):
        """Operatsiya uchun topshiriq yaratadi (test to'plamini ham tayyorlaydi)."""
        quiz, _created, message = get_or_create_quiz(loan.copy.book)
        if not quiz or not quiz.is_ready:
            if quiz:
                self.stdout.write(
                    self.style.WARNING(
                        f"    savollar yetarli emas ({quiz.questions_count} ta): {message}"
                    )
                )
            return None

        assignment = Assignment.create_for_loan(loan, quiz)
        if note:
            assignment.delivery_note = note[:255]
            assignment.save(update_fields=["delivery_note"])
        return assignment
