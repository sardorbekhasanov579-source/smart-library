"""Kitob turlari — fonddagi mayda toifalarni katta guruhlarga ajratish.

Fond faylidagi «Turi» ustunida 30 dan ortiq mayda toifa bor (Badiiy, Roman,
Darslik, O'quv qo'llanma, Monografiya ...). Kitobxonga qidirishda bularni
6 ta tushunarli guruhga yig'amiz. Guruh — oddiy yuqori toifa (`parent=None`),
mayda toifalar uning ichiga kiradi, shuning uchun mavjud filtrlar
(`Category.all_descendant_ids`) o'zgarishsiz ishlayveradi.

Tartib muhim: birinchi mos kelgan guruh tanlanadi. Masalan
«Ilmiy-uslubiy qo'llanma» — o'quv adabiyoti, chunki «qo'llanma» so'zi
«ilmiy» dan oldin tekshiriladi.
"""
import re

GROUP_DESCRIPTION = "Kitob turi (guruh)"

# (guruh nomi, kalit so'zlar). Kalit so'zlar kichik harfda, apostrof '.
KIND_GROUPS = [
    ("Badiiy adabiyot", (
        "badiiy", "roman", "qissa", "hikoya", "she'r", "sher", "doston", "drama",
        "povest", "novella", "ertak", "poeziya", "proza", "hajviy",
    )),
    ("O'quv adabiyoti", (
        "darslik", "o'quv", "oquv", "qo'llanma", "qollanma", "metodik", "uslubiy",
        "ўқув", "қўлланма", "амалий", "учебник", "пособие", "praktikum", "majmua",
        "ma'ruza", "maruza", "kurs", "xorijiy til",
    )),
    ("Ilmiy adabiyot", (
        "ilmiy", "monografiya", "монография", "risola", "maqola", "to'plam",
        "toplam", "dissertatsiya", "tezis", "avtoreferat", "научн", "tadqiqot",
    )),
    ("Ijtimoiy-siyosiy", (
        "siyosiy", "mirziyoyev", "karimov", "kodeks", "qonun", "qoida", "huquq",
        "dinshunos", "ijtimoiy", "falsafa", "tarix", "ma'naviy", "manaviy",
        "prezident", "konstitutsiya",
    )),
    ("Lug'at va ma'lumotnoma", (
        "lug'at", "lugat", "ensiklopediya", "entsiklopediya", "энциклопедия",
        "ma'lumotnoma", "malumotnoma", "справочник", "словарь", "atlas",
    )),
    ("Boshqa", ()),
]

GROUP_NAMES = [name for name, _ in KIND_GROUPS]
FALLBACK_GROUP = "Boshqa"


def _normalize(text):
    text = str(text or "").lower()
    return re.sub(r"[‘’ʻʼ`´]", "'", text)


def classify(name):
    """Mayda toifa nomi -> guruh nomi."""
    text = _normalize(name)
    for group, words in KIND_GROUPS:
        if any(word in text for word in words):
            return group
    return FALLBACK_GROUP


def group_for(category_name, Category=None):
    """Guruh toifasini qaytaradi (yo'q bo'lsa yaratadi)."""
    if Category is None:
        from apps.catalog.models import Category
    group_name = classify(category_name)
    group = Category.objects.filter(name=group_name, parent__isnull=True).first()
    if group is None:
        group = Category.objects.create(name=group_name, description=GROUP_DESCRIPTION)
    return group


def assign_groups(Category=None, only_ungrouped=True):
    """Guruhsiz yuqori toifalarni guruhlarga joylaydi.

    Ichida boshqa toifalar bor yuqori toifalarga (kutubxonachi o'zi tuzgan
    guruhlar) tegilmaydi. Nechta toifa ko'chirilganini qaytaradi.
    """
    if Category is None:
        from apps.catalog.models import Category

    groups = {}
    for name in GROUP_NAMES:
        group = Category.objects.filter(name=name, parent__isnull=True).first()
        if group is None:
            group = Category.objects.create(name=name, description=GROUP_DESCRIPTION)
        groups[name] = group
    group_ids = {g.pk for g in groups.values()}

    moved = 0
    candidates = Category.objects.filter(parent__isnull=True).exclude(pk__in=group_ids)
    for category in candidates:
        if only_ungrouped and Category.objects.filter(parent=category).exists():
            continue  # o'zi guruh vazifasini bajaryapti
        target = groups[classify(category.name)]
        # Guruh ichida xuddi shu nomli toifa bo'lsa — kitoblarni unga o'tkazamiz
        twin = Category.objects.filter(parent=target, name=category.name).first()
        if twin:
            category.books.update(category=twin)
            category.delete()
        else:
            category.parent = target
            category.save(update_fields=["parent"])
        moved += 1
    return moved
