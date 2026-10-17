"""Kitob(lar) uchun test savollarini yaratish.

Misollar:
    python manage.py generate_quiz --book-id 12
    python manage.py generate_quiz --book-id 12 --force --count 30
    python manage.py generate_quiz --issued          # hozir qo'lda bo'lgan kitoblar uchun
    python manage.py generate_quiz --due-in 1        # muddati 1 kundan keyin tugaydiganlar
    python manage.py generate_quiz --all --limit 20  # testi yo'q kitoblardan 20 tasi
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.books.models import Book
from apps.quizzes.ai import get_provider, is_configured
from apps.quizzes.services import get_or_create_quiz


class Command(BaseCommand):
    help = "Kitoblar uchun test savollarini yaratadi (AI yoki zaxira generator)"

    def add_arguments(self, parser):
        parser.add_argument("--book-id", type=int, help="Bitta kitob ID si")
        parser.add_argument("--all", action="store_true", help="Testi yo'q barcha kitoblar")
        parser.add_argument(
            "--issued", action="store_true",
            help="Hozir kitobxonlar qo'lida bo'lgan kitoblar",
        )
        parser.add_argument(
            "--due-in", type=int,
            help="Qaytarish muddati N kundan keyin tugaydigan kitoblar",
        )
        parser.add_argument("--count", type=int, help="Savollar soni (standart: sozlamadan)")
        parser.add_argument("--limit", type=int, default=0, help="Nechta kitob bilan cheklash")
        parser.add_argument("--force", action="store_true", help="Mavjud test bo'lsa ham yangilash")

    def handle(self, *args, **options):
        books = self.collect_books(options)
        if not books:
            self.stdout.write(self.style.WARNING("Mos kitob topilmadi."))
            return

        if is_configured():
            self.stdout.write(f"AI provayderi: {get_provider()}")
        else:
            self.stdout.write(
                self.style.WARNING(
                    "AI kaliti yo'q — zaxira generator ishlatiladi "
                    "(Sozlamalar > ai_api_key)."
                )
            )

        ok = weak = failed = 0
        for book in books:
            try:
                quiz, created, message = get_or_create_quiz(
                    book, force=options["force"], question_count=options["count"]
                )
            except Exception as exc:  # pragma: no cover
                failed += 1
                self.stderr.write(f"✗ {book.title}: {exc}")
                continue

            if not quiz:
                failed += 1
                self.stderr.write(f"✗ {book.title}: {message}")
                continue

            count = quiz.questions_count
            label = "yangi" if created else "mavjud"
            if count < 5:
                weak += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠ {book.title}: faqat {count} ta savol ({label}) — {message}"
                    )
                )
            else:
                ok += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✓ {book.title}: {count} ta savol ({label})")
                )

        self.stdout.write("")
        self.stdout.write(f"Tayyor: {ok} ta | Savol kam: {weak} ta | Xato: {failed} ta")
        if weak:
            self.stdout.write(
                self.style.WARNING(
                    "Savol kam bo'lgan testlarni /testlar/ bo'limida qo'lda to'ldiring."
                )
            )

    # -- kitoblarni tanlash --------------------------------------------------
    def collect_books(self, options):
        if options["book_id"]:
            book = Book.objects.filter(pk=options["book_id"]).first()
            if not book:
                raise CommandError(f"ID {options['book_id']} bo'yicha kitob topilmadi.")
            return [book]

        queryset = Book.objects.select_related("author", "category")

        if options["due_in"] is not None:
            target = timezone.localdate() + timedelta(days=options["due_in"])
            queryset = queryset.filter(
                copies__loans__return_date__isnull=True,
                copies__loans__due_date=target,
            ).distinct()
        elif options["issued"]:
            queryset = queryset.filter(copies__loans__return_date__isnull=True).distinct()
        elif options["all"]:
            if not options["force"]:
                queryset = queryset.filter(quizzes__isnull=True)
        else:
            raise CommandError(
                "Qaysi kitoblar? --book-id, --issued, --due-in yoki --all dan birini bering."
            )

        if options["limit"]:
            queryset = queryset[: options["limit"]]
        return list(queryset)
