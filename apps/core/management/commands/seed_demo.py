"""Demo ma'lumotlar bilan to'ldirish: python manage.py seed_demo"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.books.models import Book, BookCopy
from apps.catalog.models import Author, Category
from apps.core.models import SystemSetting
from apps.loans.models import Loan
from apps.readers.models import Reader
from apps.users.models import Role, User

AUTHORS = [
    ("Abdulla Qodiriy", 1894), ("Cho'lpon", 1897), ("Oybek", 1905),
    ("G'afur G'ulom", 1903), ("Alisher Navoiy", 1441), ("Said Ahmad", 1920),
    ("Pirimqul Qodirov", 1928), ("O'tkir Hoshimov", 1941),
    ("J.K. Rowling", 1965), ("George Orwell", 1903),
]

CATEGORIES = {
    "Badiiy adabiyot": ["Roman", "Hikoyalar", "She'riyat"],
    "Ilmiy adabiyot": ["Matematika", "Fizika", "Tarix"],
    "Bolalar adabiyoti": [],
    "Darsliklar": ["Oliy ta'lim", "Maktab"],
}

BOOK_TITLES = [
    "O'tkan kunlar", "Mehrobdan chayon", "Kecha va kunduz", "Qutlug' qon",
    "Sarob", "Navoiy", "Qiyomat qarz", "Daydi it", "Tun panohida",
    "Ikki eshik orasi", "Yulduzli tunlar", "Dunyoning ishlari",
    "Sariq devni minib", "Ufq", "Ming bir kecha", "Baxtiyor avlod",
    "Alpomish", "Shaytanat", "Yolg'iz odam shahri", "Nurli yo'l",
]


class Command(BaseCommand):
    help = "Demo ma'lumotlar bilan bazani to'ldiradi (mualliflar, kitoblar, kitobxonlar, operatsiyalar)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Avval demo ma'lumotlarni tozalaydi")

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Tizim sozlamalari...")
        for key, value, desc in SystemSetting.defaults():
            SystemSetting.set(key, value, desc)

        self.stdout.write("Foydalanuvchilar...")
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                username="admin", password="admin12345", full_name="Bosh Administrator"
            )
        librarian, created = User.objects.get_or_create(
            username="kutubxonachi",
            defaults=dict(full_name="Dilnoza Karimova", role=Role.LIBRARIAN),
        )
        if created:
            librarian.set_password("kutub12345")
            librarian.save()

        self.stdout.write("Mualliflar...")
        authors = []
        for name, year in AUTHORS:
            a, _ = Author.objects.get_or_create(full_name=name, defaults={"birth_year": year})
            authors.append(a)

        self.stdout.write("Toifalar...")
        categories = []
        for parent_name, children in CATEGORIES.items():
            parent, _ = Category.objects.get_or_create(name=parent_name)
            categories.append(parent)
            for child_name in children:
                child, _ = Category.objects.get_or_create(name=child_name, parent=parent)
                categories.append(child)

        self.stdout.write("Kitoblar va nusxalar...")
        books = []
        for i, title in enumerate(BOOK_TITLES):
            book, created = Book.objects.get_or_create(
                title=title,
                defaults=dict(
                    author=random.choice(authors),
                    category=random.choice(categories),
                    isbn=f"978{random.randint(1000000000, 9999999999)}",
                    publisher=random.choice(["Sharq", "Yangi asr avlodi", "O'zbekiston", "Cho'lpon nashriyoti"]),
                    publication_year=random.randint(1960, 2023),
                    shelf_location=f"{chr(65 + i % 5)}-{(i % 12) + 1}",
                    description="Avtomatik yaratilgan demo tavsif.",
                ),
            )
            books.append(book)
            if created:
                copies_n = random.randint(2, 6)
                for c in range(copies_n):
                    BookCopy.objects.create(
                        book=book,
                        inventory_number=f"INV-{book.pk:04d}-{c + 1:03d}",
                        shelf_location=book.shelf_location,
                    )
                book.recalc_quantities()

        self.stdout.write("Kitobxonlar...")
        first_names = ["Aziz", "Dilshod", "Kamola", "Nilufar", "Sardor", "Zuhra",
                       "Jasur", "Madina", "Botir", "Shoira", "Rustam", "Gulnora"]
        last_names = ["Abdullayev", "Karimova", "Rustamov", "Yusupova", "Tojiyev",
                     "Nazarova", "Saidov", "Ergasheva"]
        readers = []
        for i in range(30):
            code = Reader.generate_code()
            reader = Reader.objects.create(
                full_name=f"{random.choice(last_names)} {random.choice(first_names)}",
                reader_code=code,
                phone=f"+998 9{random.randint(0,9)} {random.randint(100,999)} {random.randint(10,99)} {random.randint(10,99)}",
                reader_type=random.choice(["student", "teacher", "employee", "other"]),
                registration_date=timezone.localdate() - timedelta(days=random.randint(1, 600)),
            )
            readers.append(reader)

        self.stdout.write("Berish/qaytarish operatsiyalari...")
        available_copies = list(BookCopy.objects.filter(status="available"))
        random.shuffle(available_copies)
        today = timezone.localdate()

        # Ba'zilarini hali qaytarilmagan (ba'zilari muddati o'tgan) qilib qoldiramiz
        for copy in available_copies[:18]:
            reader = random.choice(readers)
            days_ago = random.randint(0, 25)
            issue_date = today - timedelta(days=days_ago)
            loan_days = random.choice([7, 14, 21])
            loan = Loan.objects.create(
                reader=reader, copy=copy, issue_date=issue_date,
                due_date=issue_date + timedelta(days=loan_days),
                issued_by=librarian,
            )
            copy.status = "issued"
            copy.save(update_fields=["status"])
            copy.book.recalc_quantities()

        # Qaytarilgan tarixiy operatsiyalar
        for copy in available_copies[18:60]:
            reader = random.choice(readers)
            issue_date = today - timedelta(days=random.randint(30, 300))
            due_date = issue_date + timedelta(days=14)
            return_date = due_date - timedelta(days=random.randint(-3, 5))
            Loan.objects.create(
                reader=reader, copy=copy, issue_date=issue_date, due_date=due_date,
                return_date=return_date, status="returned",
                issued_by=librarian, received_by=librarian,
            )

        self.stdout.write(self.style.SUCCESS(
            "\nDemo ma'lumotlar tayyor!\n"
            "  Admin login:          admin / admin12345\n"
            "  Kutubxonachi login:   kutubxonachi / kutub12345\n"
        ))
