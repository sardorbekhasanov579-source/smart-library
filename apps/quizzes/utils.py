"""Testlar moduli uchun kichik yordamchi funksiyalar."""
import re


def normalize_phone(raw):
    """Telefon raqamni solishtirish uchun yagona ko'rinishga keltiradi.

    +998 (90) 123-45-67 -> 998901234567
    901234567            -> 998901234567
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return ""
    # O'zbekiston raqamlari: oxirgi 9 raqam asosiy qism
    if len(digits) == 9:
        return "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return digits
    if len(digits) > 12 and digits.endswith(digits[-12:]) and "998" in digits[-12:]:
        return digits[-12:]
    # Boshqa davlat raqamlari - borligicha qoldiramiz
    return digits


def pretty_phone(raw):
    """998901234567 -> +998 90 123 45 67"""
    d = normalize_phone(raw)
    if len(d) == 12 and d.startswith("998"):
        return f"+{d[:3]} {d[3:5]} {d[5:8]} {d[8:10]} {d[10:]}"
    return f"+{d}" if d else ""


def phone_variants(raw):
    """Bazada turli formatda saqlangan raqamlarni topish uchun variantlar."""
    d = normalize_phone(raw)
    if not d:
        return []
    out = {d, "+" + d}
    if len(d) == 12:
        tail = d[3:]
        out.update({tail, "+998" + tail, "998" + tail})
    return [v for v in out if v]
