"""Kitobxon darajalari.

Faollik ballari (apps.activity) asosida kitobxonga daraja beriladi. Daraja
qancha yuqori bo'lsa, shuncha ko'p imtiyoz: bir vaqtda ko'proq kitob olish va
uzoqroq muddat.

Darajalar bazada saqlanmaydi — ball o'zgarishi bilan o'zi qayta hisoblanadi.
Chegaralar va imtiyozlar Sozlamalar bo'limidan o'zgartiriladi.
"""
from django.db.models import Sum

# Asosiy daraja (hamma shu darajadan boshlaydi) + uchta yuqori daraja.
# Imtiyozlar ASOSIY sozlamaga QO'SHILADI: masalan standart 5 kitob bo'lsa,
# "Bilimdon" darajasidagi kitobxon 5 + 2 = 7 ta kitob ola oladi.
BASE_LEVEL = {
    "slug": "yangi",
    "name": "Yangi kitobxon",
    "min_points": 0,
    "bonus_books": 0,
    "bonus_days": 0,
    "color": "#5a6b85",
    "note": "Hamma shu darajadan boshlaydi",
}

UPPER_LEVELS = [
    {
        "slug": "faol",
        "name": "Faol kitobxon",
        "setting": "level_faol_min",
        "default_min": 20,
        "color": "#1b63c4",
    },
    {
        "slug": "bilimdon",
        "name": "Bilimdon",
        "setting": "level_bilimdon_min",
        "default_min": 60,
        "color": "#1f8a52",
    },
    {
        "slug": "oltin",
        "name": "Oltin kitobxon",
        "setting": "level_oltin_min",
        "default_min": 120,
        "color": "#b4701d",
    },
]

DEFAULT_BONUS_BOOKS = "1,2,3"
DEFAULT_BONUS_DAYS = "3,7,14"


def _numbers(value, fallback, count):
    """«1,2,3» ko'rinishidagi sozlamani sonlar ro'yxatiga aylantiradi."""
    source = (value or "").strip() or fallback
    result = []
    for part in source.split(","):
        part = part.strip()
        try:
            result.append(max(0, int(float(part))))
        except (TypeError, ValueError):
            result.append(0)
    while len(result) < count:
        result.append(0)
    return result[:count]


def level_table():
    """Barcha darajalar ro'yxati (pastdan yuqoriga)."""
    from apps.core.models import SystemSetting

    books = _numbers(
        SystemSetting.get("level_bonus_books", ""), DEFAULT_BONUS_BOOKS, 3
    )
    days = _numbers(SystemSetting.get("level_bonus_days", ""), DEFAULT_BONUS_DAYS, 3)

    table = [dict(BASE_LEVEL)]
    for index, item in enumerate(UPPER_LEVELS):
        table.append(
            {
                "slug": item["slug"],
                "name": item["name"],
                "min_points": SystemSetting.get_int(
                    item["setting"], item["default_min"]
                ),
                "bonus_books": books[index],
                "bonus_days": days[index],
                "color": item["color"],
                "note": "",
            }
        )
    # Chegaralar noto'g'ri kiritilsa ham tartib buzilmasin
    table.sort(key=lambda row: row["min_points"])
    return table


def level_for(points, table=None):
    """Ballga mos darajani qaytaradi."""
    points = points or 0
    table = table or level_table()
    current = table[0]
    for row in table:
        if points >= row["min_points"]:
            current = row
        else:
            break
    return current


def reader_points(reader):
    """Kitobxonning umumiy faollik balli."""
    try:
        return reader.activity_records.aggregate(s=Sum("points"))["s"] or 0
    except Exception:  # faollik moduli yo'q yoki jadval hali yaratilmagan
        return 0


def level_progress(points):
    """Daraja, keyingi daraja va unga qancha qolgani.

    Qaytaradi: {level, next, points, remaining, percent}
    """
    points = points or 0
    table = level_table()
    current = level_for(points, table)

    following = None
    for row in table:
        if row["min_points"] > current["min_points"]:
            following = row
            break

    if not following:
        return {
            "level": current,
            "next": None,
            "points": points,
            "remaining": 0,
            "percent": 100,
        }

    span = following["min_points"] - current["min_points"]
    done = points - current["min_points"]
    percent = 100 if span <= 0 else min(100, max(3, round(done * 100 / span)))
    return {
        "level": current,
        "next": following,
        "points": points,
        "remaining": max(0, following["min_points"] - points),
        "percent": percent,
    }


def level_for_reader(reader):
    """Kitobxonning darajasi (ball bilan birga)."""
    return level_progress(reader_points(reader))


def level_settings_defaults():
    """Sozlamalar bo'limida paydo bo'ladigan kalitlar."""
    rows = [
        (
            item["setting"],
            str(item["default_min"]),
            f"«{item['name']}» darajasi uchun kerakli ball",
        )
        for item in UPPER_LEVELS
    ]
    rows.append(
        (
            "level_bonus_books",
            DEFAULT_BONUS_BOOKS,
            "Darajalar uchun qo'shimcha kitob soni (Faol, Bilimdon, Oltin)",
        )
    )
    rows.append(
        (
            "level_bonus_days",
            DEFAULT_BONUS_DAYS,
            "Darajalar uchun qo'shimcha kun (Faol, Bilimdon, Oltin)",
        )
    )
    return rows
