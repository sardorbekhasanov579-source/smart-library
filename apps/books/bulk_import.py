"""Excel fayldan kitoblarni ommaviy qo'shish va joylashuvni yuklash.

Ikki rejim bor:

1. «Yangi kitoblar» — har bir qator kitob (soni ko'rsatilsa shuncha nusxa).
   Muallif va toifalar avtomatik guruhlanadi, yangi toifa kitob turi
   guruhiga (Badiiy, O'quv ...) o'zi joylanadi.
2. «Joylashuv» — bazadagi mavjud kitoblarga xona/javon/taxcha yozadi.
   Hech narsa yaratilmaydi. Kitob inventar raqami yoki nomi bo'yicha topiladi.

Ustun nomlari erkin: sarlavhada kalit so'z bo'lsa yetarli (pastdagi
COLUMN_HINTS). Har ikki rejim ikki bosqichli: avval tahlil (bazaga hech narsa
yozilmaydi), kutubxonachi tasdiqlagach — yozish.
"""
import re
import uuid
from pathlib import Path

from django.conf import settings

from apps.books.location import format_location, normalize_shelf, parse_location
from apps.books.models import Book, BookCopy, CopyStatus
from apps.catalog.models import Author, Category

TMP_DIR = Path(settings.BASE_DIR) / "tmp_imports"

MODE_NEW = "yangi"
MODE_LOCATION = "joy"
MODES = (MODE_NEW, MODE_LOCATION)

# Har bir maydon uchun sarlavhada izlanadigan so'zlar. Avval aniqrog'i
# tekshiriladi: masalan "kitob nomi" — "Kitob mualliflari" ustunini emas,
# aynan "Kitob nomi" ustunini topadi.
COLUMN_HINTS = {
    "inventory": ("inventar", "inventory", "inv."),
    "title": ("kitob nomi", "asar nomi", "title", "nomi", "kitob"),
    "author": ("muallif", "author"),
    "category": ("toifa", "turi", "janr", "kategoriya", "bo'lim", "fan", "tur"),
    "publisher": ("nashriyot", "publisher"),
    "year": ("nashr yili", "yili", "year", "yil"),
    "isbn": ("isbn",),
    "quantity": ("soni", "nusxa", "dona", "miqdor", "quantity", "count"),
    "room": ("xona", "хона", "room"),
    "shelf": ("javon", "stellaj", "shelf", "raf", "joylashuv", "joy", "manzil"),
    "tier": ("taxcha", "tokcha", "toxcha", "polka", "qavat", "tier"),
    "price": ("narx", "price"),
    "language": ("tili", "language"),
    "description": ("tavsif", "izoh", "description", "annotatsiya"),
}

MAX_PREVIEW_ROWS = 12
MAX_MISSING_ROWS = 40


# ---------------------------------------------------------------------------
# Yordamchilar
# ---------------------------------------------------------------------------
def _norm_header(text):
    text = str(text or "").strip().lower()
    return re.sub(r"[‘’ʻʼ`´]", "'", text)


def _pick_columns(headers):
    """Sarlavhalar ro'yxatidan har bir maydon uchun ustun raqamini topadi."""
    normalized = [_norm_header(h) for h in headers]
    found = {}
    used = set()
    for field, hints in COLUMN_HINTS.items():
        for hint in hints:  # kalit so'z bo'yicha — aniqrog'i birinchi
            index = next(
                (i for i, text in enumerate(normalized) if text and i not in used and hint in text),
                None,
            )
            if index is not None:
                found[field] = index
                used.add(index)
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


def norm_title(text):
    """Nomlarni solishtirish uchun: kichik harf, bitta probel, qo'shtirnoqsiz."""
    text = str(text or "").lower()
    text = re.sub(r"[‘’ʻʼ`´]", "'", text)
    text = re.sub(r"[«»\"“”„]", "", text)
    return re.sub(r"\s+", " ", text).strip(" .")


def load_rows(path):
    """Excel faylni o'qib, (sarlavhalar, qatorlar) qaytaradi."""
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    headers = list(next(rows, []) or [])
    return headers, list(rows)


def _row_reader(columns, row):
    def cell(field):
        idx = columns.get(field)
        if idx is None or idx >= len(row):
            return ""
        return _clean(row[idx])

    return cell


def _row_location(cell):
    """Qatordagi xona/javon/taxcha ustunlaridan joylashuv matni."""
    room = _clean_int(cell("room"))
    tier = _clean_int(cell("tier"))
    shelf_text = cell("shelf")
    shelf = normalize_shelf(shelf_text)

    if shelf_text and not shelf:
        # Javon ustunida to'liq manzil yozilgan bo'lishi mumkin: "2-xona 1A-3"
        parsed = parse_location(shelf_text)
        if parsed:
            room = room or parsed["room"]
            shelf = parsed["shelf"]
            tier = tier or parsed["tier"]
        else:
            return shelf_text[:50]  # tushunarsiz bo'lsa ham borligicha saqlaymiz
    elif shelf_text and shelf and room is None and tier is None:
        parsed = parse_location(shelf_text)
        if parsed:
            room, tier = parsed["room"], parsed["tier"]

    if room and not 0 < room < 100:
        room = None
    if tier and not 0 < tier < 100:
        tier = None
    return format_location(room, shelf, tier)


def _column_labels(headers, columns):
    return {
        field: headers[idx] for field, idx in columns.items() if idx < len(headers)
    }


# ---------------------------------------------------------------------------
# 1-rejim: yangi kitoblar
# ---------------------------------------------------------------------------
def parse_workbook(path):
    """Faylni tahlil qiladi: ustunlarni taniydi, har bir qatorni tekshiradi.

    Hech narsani bazaga yozmaydi.
    """
    headers, raw_rows = load_rows(path)
    columns = _pick_columns(headers)

    result_rows = []
    total_copies = 0

    for number, row in enumerate(raw_rows, start=2):
        cell = _row_reader(columns, row)
        title = cell("title")
        if not title:
            continue  # bo'sh qator - e'tiborsiz qoldiriladi, xato emas

        quantity = _clean_int(cell("quantity"), default=1) or 1
        quantity = max(1, min(quantity, 500))  # bitta qatordan 500 tadan ortiq nusxa bo'lmasin

        year = _clean_int(cell("year"))
        if year is not None and not (1400 <= year <= 2100):
            year = None  # ustun chalkashib ketgan bo'lsa (masalan ISBN) - yil deb yozilmaydi

        description = cell("description")
        language = cell("language")
        if language and "til" not in description.lower():
            description = (f"Tili: {language}" + (f" | {description}" if description else ""))

        entry = {
            "row_number": number,
            "title": title[:300],
            "author": (cell("author") or "Noma'lum muallif")[:200],
            "category": (cell("category") or "Boshqa")[:150],
            "publisher": cell("publisher")[:200],
            "year": year,
            "isbn": cell("isbn")[:20],
            "quantity": quantity,
            "shelf": _row_location(cell)[:50],
            "price": cell("price")[:50],
            "description": description,
        }
        result_rows.append(entry)
        total_copies += quantity

    return {
        "mode": MODE_NEW,
        "columns": columns,
        "column_labels": _column_labels(headers, columns),
        "missing_title": "title" not in columns,
        "rows": result_rows,
        "preview": result_rows[:MAX_PREVIEW_ROWS],
        "total": len(result_rows),
        "total_copies": total_copies,
        "authors_count": len({r["author"].lower() for r in result_rows}),
        "categories_count": len({r["category"].lower() for r in result_rows}),
        "located_count": sum(1 for r in result_rows if r["shelf"]),
    }


def _get_category(name, cache):
    """Toifani topadi yoki yaratadi; yangisi kitob turi guruhiga joylanadi."""
    from apps.catalog.kinds import GROUP_NAMES, group_for

    key = name.strip().lower()
    if key in cache:
        return cache[key]
    category = (
        Category.objects.filter(name__iexact=name, parent__isnull=False).first()
        or Category.objects.filter(name__iexact=name).first()
    )
    if not category:
        if name in GROUP_NAMES:
            category = group_for(name)
        else:
            category = Category.objects.create(name=name, parent=group_for(name))
    cache[key] = category
    return category


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

            category = _get_category(entry["category"], category_cache)

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
                    shelf_location=book.shelf_location,
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


# ---------------------------------------------------------------------------
# 2-rejim: mavjud kitoblarga joylashuv yozish
# ---------------------------------------------------------------------------
def _book_index():
    """Bazadagi kitoblar: nom -> [(id, muallif)], inventar -> (nusxa id, kitob id)."""
    by_title = {}
    for pk, title, author in Book.objects.values_list("id", "title", "author__full_name"):
        by_title.setdefault(norm_title(title), []).append((pk, (author or "").lower()))
    by_inventory = {}
    for pk, inv, book_id in BookCopy.objects.values_list("id", "inventory_number", "book_id"):
        by_inventory[str(inv).strip().lower()] = (pk, book_id)
        # "FOND-00123" va "00123" / "123" ko'rinishlari ham topilsin
        digits = re.sub(r"\D", "", str(inv))
        if digits:
            by_inventory.setdefault(f"#{int(digits)}", (pk, book_id))
    return by_title, by_inventory


def _match(entry, by_title, by_inventory):
    """Qatorga mos kitob(lar)ni topadi: ([book_id], copy_id | None)."""
    inventory = entry["inventory"].strip().lower()
    if inventory:
        hit = by_inventory.get(inventory)
        if not hit:
            digits = re.sub(r"\D", "", inventory)
            hit = by_inventory.get(f"#{int(digits)}") if digits else None
        if hit:
            return [hit[1]], hit[0]
    if entry["title"]:
        candidates = by_title.get(norm_title(entry["title"]), [])
        author = entry["author"].strip().lower()
        if author and len(candidates) > 1:
            narrowed = [c for c in candidates if author in c[1] or c[1] in author]
            candidates = narrowed or candidates
        if candidates:
            return [pk for pk, _ in candidates], None
    return [], None


def parse_locations(path):
    """Joylashuv faylini tahlil qiladi va bazadagi kitoblar bilan solishtiradi."""
    headers, raw_rows = load_rows(path)
    columns = _pick_columns(headers)
    by_title, by_inventory = _book_index()

    rows, missing = [], []
    no_location = 0
    book_ids = set()

    for number, row in enumerate(raw_rows, start=2):
        cell = _row_reader(columns, row)
        entry = {
            "row_number": number,
            "inventory": cell("inventory"),
            "title": cell("title")[:300],
            "author": cell("author")[:200],
            "location": _row_location(cell),
        }
        if not (entry["inventory"] or entry["title"]):
            continue
        if not entry["location"]:
            no_location += 1
            continue
        ids, copy_id = _match(entry, by_title, by_inventory)
        entry["book_ids"] = ids
        entry["copy_id"] = copy_id
        if ids:
            rows.append(entry)
            book_ids.update(ids)
        else:
            missing.append(entry)

    return {
        "mode": MODE_LOCATION,
        "columns": columns,
        "column_labels": _column_labels(headers, columns),
        "missing_key": not ({"title", "inventory"} & set(columns)),
        "missing_location": not ({"shelf", "room", "tier"} & set(columns)),
        "rows": rows,
        "preview": rows[:MAX_PREVIEW_ROWS],
        "matched": len(rows),
        "books_count": len(book_ids),
        "missing": missing[:MAX_MISSING_ROWS],
        "missing_count": len(missing),
        "no_location": no_location,
        "total": len(rows) + len(missing),
    }


def commit_locations(parsed_rows, user=None):
    """Topilgan kitoblarga joylashuvni yozadi (bitta tranzaksiyada)."""
    from django.db import transaction

    book_locations = {}   # kitob id -> joy (nomi bo'yicha topilganlar)
    copy_locations = {}   # nusxa id -> joy (inventar bo'yicha topilganlar)
    copy_books = {}
    for entry in parsed_rows:
        if entry.get("copy_id"):
            copy_locations[entry["copy_id"]] = entry["location"]
            copy_books[entry["copy_id"]] = entry["book_ids"][0]
        else:
            for pk in entry["book_ids"]:
                book_locations[pk] = entry["location"]

    # Inventar bo'yicha kelgan nusxaning kitobida joy bo'lmasa — o'shani beramiz
    for copy_id, book_id in copy_books.items():
        book_locations.setdefault(book_id, copy_locations[copy_id])

    updated_books = 0
    with transaction.atomic():
        books = Book.objects.in_bulk(list(book_locations))
        changed = []
        for pk, book in books.items():
            parsed = parse_location(book_locations[pk])
            if parsed:
                book.room, book.shelf, book.tier = parsed["room"], parsed["shelf"], parsed["tier"]
                book.shelf_location = format_location(book.room, book.shelf, book.tier)
            else:
                book.room, book.shelf, book.tier = None, "", None
                book.shelf_location = book_locations[pk][:50]
            changed.append(book)
        Book.objects.bulk_update(
            changed, ["room", "shelf", "tier", "shelf_location"], batch_size=500
        )
        updated_books = len(changed)

        # Nomi bo'yicha joy berilgan kitoblar nusxalari kitob joyini ko'rsatsin
        copy_book_ids = set(copy_books.values())
        title_matched = [pk for pk in book_locations if pk not in copy_book_ids]
        if title_matched:
            BookCopy.objects.filter(book_id__in=title_matched).update(shelf_location="")

        copies = BookCopy.objects.in_bulk(list(copy_locations))
        for pk, copy in copies.items():
            copy.shelf_location = copy_locations[pk][:50]
        BookCopy.objects.bulk_update(list(copies.values()), ["shelf_location"], batch_size=500)

    from apps.core.models import AuditLog

    AuditLog.log(
        user=user,
        action=AuditLog.Action.UPDATE,
        entity_type="book_location_import",
        details=(
            f"Excel orqali joylashuv yuklandi: {updated_books} kitob, "
            f"{len(copy_locations)} nusxa"
        ),
    )
    return {"books": updated_books, "copies": len(copy_locations)}


# ---------------------------------------------------------------------------
# Vaqtinchalik fayl
# ---------------------------------------------------------------------------
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
