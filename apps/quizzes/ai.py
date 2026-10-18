"""Kitob bo'yicha test savollarini avtomatik yaratish.

Uch provayder qo'llanadi (Sozlamalardagi `ai_provider` qiymati bo'yicha):
  * anthropic - Claude API  (kalit: ANTHROPIC_API_KEY yoki sozlamadagi ai_api_key)
  * openai    - OpenAI API  (kalit: OPENAI_API_KEY  yoki sozlamadagi ai_api_key)
  * gemini    - Google Gemini (kalit: GEMINI_API_KEY yoki sozlamadagi ai_api_key)
                Gemini'da bepul tarif bor: https://aistudio.google.com/apikey

Kalit bo'lmasa yoki so'rov muvaffaqiyatsiz bo'lsa — kitob kartasidagi
ma'lumotlar (nomi, muallifi, toifasi, nashr yili, nashriyoti, tavsifi)
asosida zaxira savollar to'plami tuziladi.
"""
import json
import logging
import os
import random
import re
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

TIMEOUT = 180

PROMPT_TEMPLATE = """Siz kutubxona uchun o'quvchining kitobni o'qiganini tekshiradigan
test tuzuvchisisiz. Quyidagi kitob bo'yicha {count} ta ko'p variantli savol tuzing.

Kitob ma'lumotlari:
- Nomi: {title}
- Muallif: {author}
- Toifa: {category}
- Nashr yili: {year}
- Nashriyot: {publisher}
- Tavsif: {description}

Qoidalar:
1. Savollar o'zbek tilida (lotin yozuvida) bo'lsin.
2. Har bir savolda aynan 4 ta variant bo'lsin, faqat bittasi to'g'ri.
3. Savollar kitob mazmunini bilishni tekshirsin: syujet, qahramonlar, asosiy
   g'oyalar, muhim voqealar, muallif va asar konteksti.
4. Faqat kitobni haqiqatan o'qigan odam javob bera oladigan savollar bo'lsin.
   Umumiy, taxmin qilib topiladigan savollardan saqlaning.
5. Noto'g'ri variantlar ham ishonchli ko'rinsin.
6. Har bir savolga qisqa izoh (to'g'ri javob nega to'g'ri) qo'shing.

Javobni FAQAT quyidagi ko'rinishdagi JSON massiv sifatida qaytaring,
boshqa hech qanday matn qo'shmang:

[
  {{
    "text": "Savol matni?",
    "choices": ["Variant A", "Variant B", "Variant C", "Variant D"],
    "correct_index": 0,
    "explanation": "Qisqa izoh"
  }}
]
"""


# ---------------------------------------------------------------------------
# Sozlamalar
# ---------------------------------------------------------------------------
def _setting(key, default=""):
    from apps.core.models import SystemSetting

    return (SystemSetting.get(key, default) or default or "").strip()


def get_provider():
    return (_setting("ai_provider", "anthropic") or "anthropic").lower()


def get_api_key(provider=None):
    provider = provider or get_provider()
    key = _setting("ai_api_key", "")
    if key:
        return key
    if provider == "openai":
        return (os.environ.get("OPENAI_API_KEY", "") or "").strip()
    if provider == "gemini":
        return (
            os.environ.get("GEMINI_API_KEY", "")
            or os.environ.get("GOOGLE_API_KEY", "")
            or ""
        ).strip()
    return (os.environ.get("ANTHROPIC_API_KEY", "") or "").strip()


DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
}


def get_model(provider=None):
    provider = provider or get_provider()
    model = _setting("ai_model", "")
    if model:
        return model
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS["anthropic"])


def is_configured():
    return bool(get_api_key())


# ---------------------------------------------------------------------------
# HTTP yordamchisi
# ---------------------------------------------------------------------------
def _post_json(url, payload, headers, timeout=TIMEOUT):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")[:500]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ulanib bo'lmadi: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Provayderlar
# ---------------------------------------------------------------------------
def _call_anthropic(prompt, api_key, model):
    body = _post_json(
        "https://api.anthropic.com/v1/messages",
        {
            "model": model,
            "max_tokens": 16000,
            "messages": [{"role": "user", "content": prompt}],
        },
        {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    parts = body.get("content") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def _call_openai(prompt, api_key, model):
    body = _post_json(
        "https://api.openai.com/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        },
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    choices = body.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "")


def _call_gemini(prompt, api_key, model):
    """Google Gemini (Generative Language API). Bepul tarifi bor."""
    body = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                # Javob to'g'ridan-to'g'ri JSON bo'lib kelsin
                "responseMimeType": "application/json",
            },
        },
        {"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    candidates = body.get("candidates") or []
    if not candidates:
        # Ba'zan xavfsizlik filtri tufayli javob bo'lmaydi
        reason = (body.get("promptFeedback") or {}).get("blockReason")
        if reason:
            raise RuntimeError(f"Gemini javobni bloklandi: {reason}")
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


# ---------------------------------------------------------------------------
# JSON ni ajratib olish
# ---------------------------------------------------------------------------
def extract_questions(raw_text):
    """Model javobidan savollar massivini ajratib oladi."""
    if not raw_text:
        return []
    text = raw_text.strip()
    # ```json ... ``` bloklarini tozalash
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        question_text = str(item.get("text") or item.get("question") or "").strip()
        choices = item.get("choices") or item.get("options") or []
        if isinstance(choices, dict):
            choices = list(choices.values())
        choices = [str(c).strip() for c in choices if str(c).strip()]
        if not question_text or len(choices) < 2:
            continue
        try:
            correct = int(item.get("correct_index", item.get("answer_index", 0)))
        except (TypeError, ValueError):
            correct = 0
        if not 0 <= correct < len(choices):
            correct = 0
        cleaned.append(
            {
                "text": question_text,
                "choices": choices[:6],
                "correct_index": correct if correct < 6 else 0,
                "explanation": str(item.get("explanation") or "").strip(),
            }
        )
    return cleaned


# ---------------------------------------------------------------------------
# Asosiy funksiya
# ---------------------------------------------------------------------------
def generate_questions(book, count=30):
    """(savollar, manba, xabar) qaytaradi. Manba: 'ai' yoki 'fallback'."""
    provider = get_provider()
    api_key = get_api_key(provider)
    if not api_key:
        questions = build_fallback_questions(book, count)
        return (
            questions,
            "fallback",
            "AI kaliti kiritilmagan — savollar kitob kartasi asosida tuzildi. "
            "Sozlamalarda `ai_api_key` ni to'ldirsangiz mazmunli savollar yaratiladi.",
        )

    prompt = PROMPT_TEMPLATE.format(
        count=count,
        title=book.title,
        author=book.author.full_name if book.author_id else "—",
        category=str(book.category) if book.category_id else "—",
        year=book.publication_year or "—",
        publisher=book.publisher or "—",
        description=(book.description or "—")[:1500],
    )

    try:
        if provider == "openai":
            raw = _call_openai(prompt, api_key, get_model(provider))
        elif provider == "gemini":
            raw = _call_gemini(prompt, api_key, get_model(provider))
        else:
            raw = _call_anthropic(prompt, api_key, get_model(provider))
    except RuntimeError as exc:
        logger.warning("AI so'rovi muvaffaqiyatsiz: %s", exc)
        return (
            build_fallback_questions(book, count),
            "fallback",
            f"AI javob bermadi ({exc}). Zaxira savollar tuzildi.",
        )

    questions = extract_questions(raw)
    if not questions:
        return (
            build_fallback_questions(book, count),
            "fallback",
            "AI javobi tushunarsiz bo'ldi. Zaxira savollar tuzildi.",
        )
    return questions[:count], "ai", f"AI {len(questions[:count])} ta savol yaratdi."


# ---------------------------------------------------------------------------
# Zaxira generator (AI bo'lmaganda)
# ---------------------------------------------------------------------------
def _distractors(correct, pool, needed=3):
    """To'g'ri javobdan farq qiluvchi variantlar tanlaydi."""
    options = [str(p) for p in pool if str(p) and str(p) != str(correct)]
    random.shuffle(options)
    out = options[:needed]
    filler = ["Ma'lumot ko'rsatilmagan", "Boshqa javob", "Aniq emas", "Hech biri"]
    i = 0
    while len(out) < needed and i < len(filler):
        if filler[i] not in out:
            out.append(filler[i])
        i += 1
    return out


def _make(text, correct, distractors, explanation=""):
    choices = [correct] + list(distractors)
    random.shuffle(choices)
    return {
        "text": text,
        "choices": [str(c)[:490] for c in choices],
        "correct_index": choices.index(correct),
        "explanation": explanation,
    }


def build_fallback_questions(book, count=30):
    """Kitob kartasidagi ma'lumotlar asosida savollar tuzadi.

    Diqqat: bu savollar kitob mazmunini emas, kitob haqidagi ma'lumotlarni
    tekshiradi. To'liq tekshiruv uchun AI kalitini ulash yoki savollarni
    qo'lda kiritish tavsiya etiladi.
    """
    from apps.books.models import Book

    questions = []
    author_name = book.author.full_name if book.author_id else ""
    category_name = str(book.category) if book.category_id else ""

    other_authors = list(
        Book.objects.exclude(pk=book.pk)
        .select_related("author")
        .order_by("?")
        .values_list("author__full_name", flat=True)[:30]
    )
    other_titles = list(
        Book.objects.exclude(pk=book.pk).order_by("?").values_list("title", flat=True)[:30]
    )
    other_categories = list(
        Book.objects.exclude(pk=book.pk)
        .select_related("category")
        .order_by("?")
        .values_list("category__name", flat=True)[:30]
    )
    other_publishers = [
        p for p in Book.objects.exclude(pk=book.pk).order_by("?")
        .values_list("publisher", flat=True)[:30] if p
    ]

    if author_name:
        questions.append(
            _make(
                f"«{book.title}» asarining muallifi kim?",
                author_name,
                _distractors(author_name, other_authors),
                f"Asar muallifi — {author_name}.",
            )
        )
        questions.append(
            _make(
                f"{author_name} qalamiga mansub quyidagi asarni toping:",
                book.title,
                _distractors(book.title, other_titles),
                f"«{book.title}» — {author_name} asari.",
            )
        )
    if category_name:
        questions.append(
            _make(
                f"«{book.title}» kitobi qaysi toifaga kiradi?",
                category_name,
                _distractors(category_name, other_categories),
                f"Kitob «{category_name}» toifasida.",
            )
        )
    if book.publication_year:
        year = book.publication_year
        questions.append(
            _make(
                f"«{book.title}» kitobi qaysi yilda nashr etilgan?",
                str(year),
                [str(year - 3), str(year + 2), str(year - 7)],
                f"Nashr yili — {year}.",
            )
        )
    if book.publisher:
        questions.append(
            _make(
                f"«{book.title}» kitobini qaysi nashriyot chiqargan?",
                book.publisher,
                _distractors(book.publisher, other_publishers),
                f"Nashriyot — {book.publisher}.",
            )
        )
    if book.isbn:
        questions.append(
            _make(
                f"«{book.title}» kitobining ISBN raqami qaysi?",
                book.isbn,
                _distractors(book.isbn, ["978-9943-00-000-1", "978-9943-11-222-3",
                                         "978-9943-55-666-7"]),
                f"ISBN — {book.isbn}.",
            )
        )

    # Tavsifdagi gaplar asosida savollar
    description = (book.description or "").strip()
    if description:
        sentences = [s.strip() for s in re.split(r"[.!?]\s+", description) if len(s.strip()) > 30]
        for sentence in sentences[:10]:
            words = [w for w in re.findall(r"[\w'’]+", sentence) if len(w) > 5]
            if not words:
                continue
            keyword = random.choice(words)
            masked = sentence.replace(keyword, "______", 1)
            questions.append(
                _make(
                    f"Kitob tavsifidagi bo'sh joyni to'ldiring:\n«{masked}»",
                    keyword,
                    _distractors(keyword, words),
                    f"To'g'ri so'z — «{keyword}».",
                )
            )

    # Diqqat: sun'iy "to'ldiruvchi" savollar qo'shilmaydi — ular testni
    # ma'nosiz qilib qo'yadi. Savollar yetmasa, kutubxonachi qo'lda qo'shadi
    # yoki AI kaliti ulanadi.
    random.shuffle(questions)
    return questions[:count]
