"""Kitoblarning javon manzilini Excel yoki CSV fayldan ommaviy yuklaydi.

Kitobxon ilovasidagi "kitob qayerda turgani" shu maydondan olinadi, shuning
uchun fondni bir marta belgilab olish kerak.

Fayl ko'rinishi (birinchi qator — sarlavha, nomlar erkin yozilsa ham bo'ladi):

    inventar      | javon
    ------------- | ---------
    000123        | A-12-3
    000124        | A-12-4

yoki inventar raqam o'rniga kitob nomi bilan:

    kitob nomi              | javon
    ----------------------- | ---------
    Fizika asoslari         | B-04-1

Ishlatish:
    python manage.py javon_yuklash javonlar.xlsx
    python manage.py javon_yuklash javonlar.xlsx --quruq     # yozmasdan sinab ko'rish
    python manage.py javon_yuklash javonlar.csv --varaq 2
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.books.models import Book, BookCopy

# Sarlavhada izlanadigan nomlar (kichik harfda, qisman mos kelishi yetarli)
INVENTORY_HEADERS = ("inventar", "inventory", "inv", "nusxa raqam", "kod")
SHELF_HEADERS = ("javon", "shelf", "joy", "manzil", "raf", "stellaj")
TITLE_HEADERS = ("kitob", "nom", "title", "asar")


def _pick(headers, wanted):
    """Sarlavhalar ro'yxatidan mos ustun raqamini topadi."""
    for index, name in enumerate(headers):
        text = str(name or "").strip().lower()
        if not text:
            continue
        for key in wanted:
            if key in text:
                return index
    return None


def _rows_from_xlsx(path, sheet_index):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise CommandError(
            "openpyxl o'rnatilmagan. Buyruq: pip install openpyxl"
        ) from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheets = workbook.worksheets
    if sheet_index < 1 or sheet_index > len(sheets):
        raise CommandError(
            f"Faylda {len(sheets)} ta varaq bor, {sheet_index}-varaq yo'q."
        )
    sheet = sheets[sheet_index - 1]
    for row in sheet.iter_rows(values_only=True):
        yield list(row)


def _rows_from_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
        for row in csv.reader(handle, dialect):
            yield row


class Command(BaseCommand):
    help = "Javon manzillarini Excel yoki CSV fayldan yuklaydi"

    def add_arguments(self, parser):
        parser.add_argument("fayl", help="Excel (.xlsx) yoki CSV fayl manzili")
        parser.add_argument(
            "--varaq",
            type=int,
            default=1,
            help="Excel faylning qaysi varag'i (standart: 1)",
        )
        parser.add_argument(
            "--quruq",
            action="store_true",
            help="Bazaga yozmaydi, faqat nima bo'lishini ko'rsatadi",
        )

    def handle(self, *args, **options):
        path = Path(options["fayl"]).expanduser()
        if not path.exists():
            raise CommandError(f"Fayl topilmadi: {path}")

        if path.suffix.lower() in (".xlsx", ".xlsm"):
            rows = _rows_from_xlsx(path, options["varaq"])
        elif path.suffix.lower() in (".csv", ".txt"):
            rows = _rows_from_csv(path)
        else:
            raise CommandError("Faqat .xlsx yoki .csv fayl qabul qilinadi.")

        rows = iter(rows)
        headers = next(rows, None)
        if headers is None:
            raise CommandError("Fayl bo'sh.")

        inv_col = _pick(headers, INVENTORY_HEADERS)
        shelf_col = _pick(headers, SHELF_HEADERS)
        title_col = _pick(headers, TITLE_HEADERS)

        if shelf_col is None:
            raise CommandError(
                "Javon ustuni topilmadi. Sarlavhada «javon» so'zi bo'lishi kerak."
            )
        if inv_col is None and title_col is None:
            raise CommandError(
                "Inventar raqam yoki kitob nomi ustuni topilmadi. "
                "Sarlavhaga «inventar» yoki «kitob nomi» deb yozing."
            )

        self.stdout.write(
            "Ustunlar: "
            + ", ".join(
                filter(
                    None,
                    [
                        f"inventar={headers[inv_col]}" if inv_col is not None else "",
                        f"kitob={headers[title_col]}" if title_col is not None else "",
                        f"javon={headers[shelf_col]}",
                    ],
                )
            )
        )

        copies_done = 0
        books_done = 0
        skipped = 0
        missing = []

        with transaction.atomic():
            for number, row in enumerate(rows, start=2):
                shelf = self._cell(row, shelf_col)
                if not shelf:
                    skipped += 1
                    continue

                inventory = self._cell(row, inv_col)
                title = self._cell(row, title_col)

                if inventory:
                    copy = BookCopy.objects.filter(
                        inventory_number=inventory
                    ).select_related("book").first()
                    if not copy:
                        missing.append(f"{number}-qator: inventar {inventory}")
                        continue
                    if not options["quruq"]:
                        copy.shelf_location = shelf
                        copy.save(update_fields=["shelf_location"])
                        if not copy.book.shelf_location:
                            copy.book.shelf_location = shelf
                            copy.book.save(update_fields=["shelf_location"])
                    copies_done += 1
                    continue

                books = list(Book.objects.filter(title__iexact=title)[:5])
                if not books:
                    missing.append(f"{number}-qator: «{title}»")
                    continue
                for book in books:
                    if not options["quruq"]:
                        book.shelf_location = shelf
                        book.save(update_fields=["shelf_location"])
                        book.copies.filter(shelf_location="").update(
                            shelf_location=shelf
                        )
                    books_done += 1

            if options["quruq"]:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Nusxa belgilandi : {copies_done}"))
        self.stdout.write(self.style.SUCCESS(f"Kitob belgilandi : {books_done}"))
        if skipped:
            self.stdout.write(f"Javoni bo'sh qatorlar: {skipped}")
        if missing:
            self.stdout.write(
                self.style.WARNING(f"Topilmadi: {len(missing)} ta qator")
            )
            for line in missing[:15]:
                self.stdout.write(f"  - {line}")
            if len(missing) > 15:
                self.stdout.write(f"  ... va yana {len(missing) - 15} ta")

        if options["quruq"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nQuruq rejim: bazaga hech narsa yozilmadi. "
                    "Haqiqiy yuklash uchun --quruq ni olib tashlang."
                )
            )

    @staticmethod
    def _cell(row, index):
        if index is None or index >= len(row):
            return ""
        value = row[index]
        if value is None:
            return ""
        return str(value).strip()
