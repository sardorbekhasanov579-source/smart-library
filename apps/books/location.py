"""Kitobning kutubxonadagi joyi: Xona -> Javon -> Taxcha.

Kutubxona tuzilishi:
  * bir nechta xona (1, 2, 3 ...);
  * har xonada javonlar qator-qator turadi. Qator harf bilan (A, B, C ...),
    qatordagi javon raqam bilan belgilanadi: 1A, 2A, 3A ... 1B, 2B ...
    Har xonada nomlash 1A dan qaytadan boshlanadi;
  * har bir javonning taxchalari (polkalari) raqamlangan: 1, 2, 3 ...

Bazada `Book.room`, `Book.shelf`, `Book.tier` maydonlarida saqlanadi va
`shelf_location` matni avtomatik yig'iladi: «2-xona · 1A · 3-taxcha».

Eski yoki qo'lda yozilgan matnni ham tushunadi:
    "2-xona 1A-3", "2/1A/3", "X2-1A-3", "xona 2, javon 1A, taxcha 3",
    "1A-3" (xonasiz), "1A" (faqat javon)
"""
import re

ROOM_WORDS = r"(?:xona|хона|room)"
TIER_WORDS = r"(?:taxcha|tokcha|toxcha|polka|qavat|ярус|полка|токча|тахча)"

# Javon: raqam + bitta lotin harfi (1A, 12B). Kirillcha A/B/C/... ham qabul.
_CYR_TO_LAT = str.maketrans({
    "а": "a", "в": "b", "с": "c", "е": "e", "н": "h", "к": "k", "м": "m",
    "о": "o", "р": "p", "т": "t", "х": "x", "б": "b", "д": "d", "г": "g",
})
SHELF_RE = re.compile(r"(?<!\d)(\d{1,3})\s*-?\s*([a-z])(?![a-z])")


def _clean_int(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def normalize_shelf(value):
    """'1 a', '1-A', '1а' -> '1A'. Tushunarsiz bo'lsa ''."""
    text = str(value or "").strip().lower().translate(_CYR_TO_LAT)
    if not text:
        return ""
    match = SHELF_RE.search(text)
    if not match:
        return ""
    return f"{int(match.group(1))}{match.group(2).upper()}"


def parse_location(text):
    """Matndan {room, shelf, tier} ajratadi. Hech narsa topilmasa None."""
    raw = str(text or "").strip()
    if not raw:
        return None
    # Xona/taxcha so'zlari kirill yoki lotinda bo'lishi mumkin — avval ularni
    # asl matndan izlaymiz, keyin javon harfi uchun kirillni lotinga o'giramiz
    low = raw.lower().replace("’", "'").replace("ʻ", "'")
    room = tier = None

    match = (
        re.search(rf"(\d{{1,2}})\s*-?\s*{ROOM_WORDS}", low)
        or re.search(rf"{ROOM_WORDS}\s*[-:№#]?\s*(\d{{1,2}})", low)
        or re.match(r"\s*[xх]\s*(\d{1,2})(?!\d)\s*[-/,. ]", low)
    )
    if match:
        room = _clean_int(match.group(1))
        low = low[: match.start()] + " " + low[match.end():]

    match = re.search(rf"(\d{{1,3}})\s*-?\s*{TIER_WORDS}", low) or re.search(
        rf"{TIER_WORDS}\s*[-:№#]?\s*(\d{{1,3}})", low
    )
    if match:
        tier = _clean_int(match.group(1))
        low = low[: match.start()] + " " + low[match.end():]

    # "javon" so'zini olib tashlaymiz, aks holda "javon 1a" dagi harflar xalaqit
    low = re.sub(r"javon|жавон|stellaj|shelf|raf", " ", low).translate(_CYR_TO_LAT)

    match = SHELF_RE.search(low)
    if not match:
        if room or tier:
            return {"room": room, "shelf": "", "tier": tier}
        return None

    shelf = f"{int(match.group(1))}{match.group(2).upper()}"
    before, after = low[: match.start()], low[match.end():]
    if room is None:
        numbers = re.findall(r"\d{1,2}", before)
        if numbers:
            room = _clean_int(numbers[-1])
    if tier is None:
        numbers = re.findall(r"\d{1,3}", after)
        if numbers:
            tier = _clean_int(numbers[0])
    return {"room": room, "shelf": shelf, "tier": tier}


def format_location(room=None, shelf="", tier=None):
    """Bazada saqlanadigan qisqa matn: «2-xona · 1A · 3-taxcha»."""
    parts = []
    if room:
        parts.append(f"{room}-xona")
    if shelf:
        parts.append(shelf)
    if tier:
        parts.append(f"{tier}-taxcha")
    return " · ".join(parts)


def location_parts(text):
    """Ko'rsatish uchun bo'laklar: [{"k": "Xona", "v": "2"}, ...].

    Tushunib bo'lmaydigan eski matn bo'lsa — borligicha bitta bo'lak.
    """
    parsed = parse_location(text)
    if not parsed or not (parsed["shelf"] or parsed["room"]):
        return [{"k": "Joy", "v": str(text)}] if text else []
    parts = []
    if parsed["room"]:
        parts.append({"k": "Xona", "v": str(parsed["room"])})
    if parsed["shelf"]:
        parts.append({"k": "Javon", "v": parsed["shelf"]})
    if parsed["tier"]:
        parts.append({"k": "Taxcha", "v": str(parsed["tier"])})
    return parts


def shelf_sort_key(shelf):
    """'2B' -> ('B', 2): avval qator harfi, keyin raqam."""
    match = re.match(r"(\d+)([A-Z])", shelf or "")
    if not match:
        return ("~", 0)
    return (match.group(2), int(match.group(1)))
