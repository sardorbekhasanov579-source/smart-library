"""Excel fayldan kitoblarni ommaviy qo'shish.

Admin yoki kutubxonachi bitta Excel faylni yuklaydi (minglab qator bo'lishi
mumkin). Tizim ustun nomlarini o'zi taniydi (qattiq shablon talab qilmaydi),
muallif va toifalarni avtomatik guruhlab (get_or_create), har bir kitob
uchun kerakli sondagi nusxa (inventar raqami bilan) yaratadi.

Ikki bosqich:
  1) parse_workbook()  - faylni o'qiydi, nima bo'lishini ko'rsatadi (hech narsa
     yozilmaydi)
  2) commit_rows()     - haqiqiy yozish, faqat admin "Tasdiqlash"ni bosgach
"""
import re
import uuid
from pathlib import Path

from django.conf import settings

from apps.books.models import Book, BookCopy, CopyStatus
from apps.catalog.models import Author, Category

TMP_DIR = Path(settings.BASE_DIR) / "tmp_imports"

# Ustun sarlavhasida izlanadigan kalit so'zlar (kichik harfda, tartib muhim —
# aniqrogi avval tekshiriladi, shuning uchun "muallif" "nomi" dan oldin kelishi
# kerak emas, lekin har biri boshqa ustunga mos kelgani uchun ziddiyat yo'q).
COLUMN_HINTS = {
    "title": ("kitob nomi", "nomi", "title", "asar nomi", "kitob"),
    "author": ("muallif", "author"),
    "category": ("toifa", "tur", "janr", "kategoriya", "bo'lim", "fan"),
    "publisher": ("nashriyot", "publisher"),
    "year": ("yil", "year"),
    "isbn": ("isbn",),
    "quantity": ("soni", "nusxa", "dona", "miqdor", "quantity", "count"),
    "shelf": ("javon", "joy", "manzil", "raf", "stellaj", "shelf"),
    "price": ("narx", "price"),
    "language": ("til", "language"),
    "description": ("tavsif", "izoh", "description", "annotatsiya"),
}

MAX_PREVIEW_ROWS = 12
MAX_ERROR_ROWS = 30


def _pick_columns(headers):
    """Sarlavhalar ro'yxatidan har bir maydon uchun ustun raqamini topadi."""
    normalized = [str(h or "").strip().lower() for h in headers]
    found = {}
    for field, hints in COLUMN_HINTS.items():
        for index, text in enumerate(normalized):
            if not text or index in found.values():
                continue
            if any(hint in text for hint in hints):
                found[field] = index
                break
    return found


def _clean(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return str(value).strip()


def _clean_int(value, default=None):
    text = _clean(value)
    if not text:
        return default
    match = re.search(r"-?\d+", text.replace(" ", ""))
    if not match:
        return default
    try:
        return int(match.group())
    except ValueError:
        return default


def load_rows(path):
    """Excel faylni o'qib, (sarlavhalar, qatorlar) qaytaradi."""
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    headers = list(next(rows, []) or [])
    return headers, list(rows)


def parse_workbook(path):
    """Faylni tahlil qiladi: ustunlarni taniydi, har bir qatorni tekshiradi.

    Hech narsani bazaga yozmaydi. Natija:
      {
        "columns": {field: ustun_nomi}, "missing_title": bool,
        "rows": [{"row_number", "title", "author", "category", ..., "ok", "error"}],
        "total": int, "valid": int, "total_copies": int,
        "preview": rows[:12],
      }
    """
    headers, raw_rows = load_rows(path)
    columns = _pick_columns(headers)

    result_rows = []
    valid = 0
    total_copies = 0

    for number, row in enumerate(raw_rows, start=2):
        def cell(field):
            idx = columns.get(field)
            if idx is None or idx >= len(row):
                return ""
            return _clean(row[idx])

        title = cell("title")
        if not title:
            continue  # bo'sh qator - e'tiborsiz qoldiriladi, xato emas

        quantity = _clean_int(cell("quantity"), default=1) or 1
        quantity = max(1, min(quantity, 500))  # bitta qatordan 500 tadan ortiq nusxa bo'lmasin

        year = _clean_int(cell("year"))
        if year is not None and not (1400 <= year <= 2100):
            year = None  # ustun chalkashib ketgan bo'lsa (masalan ISBN) - yil deb yozilmaydi

        entry = {
            "row_number": number,
            "title": title[:300],
            "author": (cell("author") or "Noma'lum muallif")[:200],
            "category": (cell("category") or "Boshqa")[:150],
            "publisher": cell("publisher")[:200],
            "year": year,
            "isbn": cell("isbn")[:20],
            "quantity": quantity,
            "shelf": cell("shelf")[:50],
            "price": cell("price")[:50],
            "description": cell("description"),
        }
        result_rows.append(entry)
        valid += 1
        total_copies += quantity

    return {
        "columns": columns,
        "column_labels": {
            field: headers[idx] for field, idx in columns.items() if idx < len(headers)
        },
        "missing_title": "title" not in columns,
        "rows": result_rows,
        "preview": result_rows[:MAX_PREVIEW_ROWS],
        "total": len(result_rows),
        "total_copies": total_copies,
        "authors_count": len({r["author"] for r in result_rows}),
        "categories_count": len({r["category"] for r in result_rows}),
    }


def save_temp_file(uploaded_file):
    """Yuklangan faylni vaqtinchalik saqlaydi, tasdiqlanmaguncha turadi."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    dest = TMP_DIR / f"{token}.xlsx"
    with open(dest, "wb") as handle:
        for chunk in uploaded_file.chunks():
            handle.write(chunk)
    return token


def temp_file_path(token):
    # token faqat hex belgilardan iborat bo'lishi kerak - papkadan chiqib
    # ketadigan yo'l (../..) berilmasligi uchun
    if not re.fullmatch(r"[0-9a-f]{32}", token or ""):
        return None
    path = TMP_DIR / f"{token}.xlsx"
    return path if path.exists() else None


def discard_temp_file(token):
    path = temp_file_path(token)
    if path:
        path.unlink(missing_ok=True)


def next_inventory_number():
    """Oxirgi avtomatik inventar raqamidan keyingisini topadi (KT-000123)."""
    last = (
        BookCopy.objects.filter(inventory_number__startswith="KT-")
        .order_by("-inventory_number")
        .values_list("inventory_number", flat=True)
        .first()
    )
    next_n = 1
    if last:
        match = re.search(r"(\d+)$", last)
        if match:
            next_n = int(match.group()) + 1
    return next_n


def commit_rows(parsed_rows, user=None):
    """Tahlil qilingan qatorlarni bazaga yozadi. (natija hisobotini qaytaradi)"""
    from django.db import transaction

    created_books = 0
    reused_books = 0
    created_copies = 0
    counter = next_inventory_number()

    author_cache = {}
    category_cache = {}
    touched_book_ids = set()

    with transaction.atomic():
        for entry in parsed_rows:
            author_key = entry["author"].strip().lower()
            author = author_cache.get(author_key)
            if not author:
                author = Author.objects.filter(
                    full_name__iexact=entry["author"]
                ).first()
                if not author:
                    author = Author.objects.create(full_name=entry["author"])
                author_cache[author_key] = author

            category_key = entry["category"].strip().lower()
            category = category_cache.get(category_key)
            if not category:
                category = Category.objects.filter(
                    name__iexact=entry["category"]
                ).first()
                if not category:
                    category = Category.objects.create(name=entry["category"])
                category_cache[category_key] = category

            book = Book.objects.filter(
                title__iexact=entry["title"], author=author
            ).first()
            if book:
                reused_books += 1
                # Bo'sh maydonlarni yangi ma'lumot bilan to'ldiramiz (ustidan yozmaymiz)
                changed = []
                if not book.shelf_location and entry["shelf"]:
                    book.shelf_location = entry["shelf"]
                    changed.append("shelf_location")
                if not book.isbn and entry["isbn"]:
                    book.isbn = entry["isbn"]
                    changed.append("isbn")
                if changed:
                    book.save(update_fields=changed)
            else:
                book = Book.objects.create(
                    title=entry["title"],
                    author=author,
                    category=category,
                    publisher=entry["publisher"],
                    publication_year=entry["year"],
                    isbn=entry["isbn"],
                    shelf_location=entry["shelf"],
                    price=entry["price"],
                    description=entry["description"],
                )
                created_books += 1

            touched_book_ids.add(book.pk)

            for _ in range(entry["quantity"]):
                inventory_number = f"KT-{counter:06d}"
                while BookCopy.objects.filter(
                    inventory_number=inventory_number
                ).exists():
                    counter += 1
                    inventory_number = f"KT-{counter:06d}"
                BookCopy.objects.create(
                    book=book,
                    inventory_number=inventory_number,
                    shelf_location=entry["shelf"],
                    status=CopyStatus.AVAILABLE,
                )
                counter += 1
                created_copies += 1

    # Nusxa sonlarini qayta hisoblash (tranzaksiyadan tashqarida - tezroq)
    for book in Book.objects.filter(pk__in=touched_book_ids):
        book.recalc_quantities()

    from apps.core.models import AuditLog

    AuditLog.log(
        user=user,
        action=AuditLog.Action.CREATE,
        entity_type="book_bulk_import",
        details=(
            f"Excel orqali ommaviy qo'shish: {created_books} yangi kitob, "
            f"{reused_books} mavjud kitobga qo'shildi, {created_copies} nusxa yaratildi"
        ),
    )

    return {
        "created_books": created_books,
        "reused_books": reused_books,
        "created_copies": created_copies,
    }
