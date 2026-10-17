# Smart Library — Kutubxona boshqaruv tizimi

Django asosida qurilgan to'liq kutubxona boshqaruv tizimi: kitoblar fondi, kitobxonlar,
kitob berish/qaytarish, hisobotlar — hamda **kitob o'qilganini tekshiruvchi test tizimi**
Telegram bot va telefonga o'rnatiladigan ilova (PWA) bilan.

![Django](https://img.shields.io/badge/Django-5.x-092E20) ![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB) ![License](https://img.shields.io/badge/license-MIT-blue)

---

## Nima qiladi

Kutubxonachi uchun klassik boshqaruv tizimi, ustiga bitta qiziq qo'shimcha: kitob
qaytarish muddati yaqinlashganda kitobxonga **o'sha kitob bo'yicha test** Telegram orqali
yuboriladi. Belgilangan foizdan yuqori natija — "kitob o'qilgan", past natija yoki
javobsiz qolgan test — "o'qimagan" xabari kutubxonachiga boradi.

```
Kitob berildi (8 kunga)
        │  7-kuni: rejalashtiruvchi ishga tushadi
        ▼
Test to'plami tanlanadi (yoki AI yaratadi)
        ▼
Kitobxonga Telegramda maxfiy havola yuboriladi
        ▼
Kitobxon 30 ta savolga javob beradi
        ├── ≥ 70%  →  kutubxonachiga "✅ Kitob o'qilgan"
        ├── < 70%  →  "❌ Kitob o'qilmagan ko'rinadi"
        └── muddat →  "⌛️ Test ishlanmadi"
```

---

## Modullar

| Modul | Nima qiladi |
|---|---|
| **Dashboard** | Umumiy statistika, oylik grafik, diqqat talab qiladigan ro'yxatlar |
| **Kitoblar** | Fond, nusxalar (inventar raqam, QR kod), muqovalar |
| **Katalog** | Mualliflar va ierarxik toifalar |
| **Kitobxonlar** | Ro'yxatga olish, holat (faol/bloklangan/arxivlangan), aqlli o'chirish |
| **Operatsiyalar** | Kitob berish/qaytarish, muddat uzaytirish, muddati o'tganlar |
| **Hisobotlar** | Fond, qarzdorlar, mashhur kitoblar — Excel va PDF eksport |
| **Testlar** | Kitob bo'yicha savollar, topshiriqlar, natijalar |
| **Telegram bot** | Kitobxonni ulash, test yuborish, natijani adminga xabar qilish |
| **Kitobxon ilovasi** | Telefon + kod bilan kirish, kitoblar, testlar (PWA) |
| **Foydalanuvchilar** | 3 ta rol: Administrator, Kutubxonachi, Kitobxon |
| **Sozlamalar** | Berish muddati, limitlar, test qoidalari, tokenlar |
| **Amallar jurnali** | Har bir muhim amal yozib boriladi |

---

## O'rnatish (o'z kompyuteringizda)

```bash
# 1. Virtual muhit
python -m venv venv
venv\Scripts\activate            # Linux/Mac: source venv/bin/activate

# 2. Kutubxonalar
pip install -r requirements.txt

# 3. Sozlamalar fayli (ixtiyoriy — standart SQLite ishlatiladi)
copy .env.example .env           # Linux/Mac: cp .env.example .env

# 4. Baza
python manage.py migrate

# 5. Demo ma'lumotlar (ixtiyoriy)
python manage.py seed_demo

# 6. Ishga tushirish
python manage.py runserver
```

Brauzerda: **http://127.0.0.1:8000/**

`seed_demo` ishlatilgan bo'lsa:

| Rol | Login | Parol |
|---|---|---|
| Administrator | `admin` | `admin12345` |
| Kutubxonachi | `kutubxonachi` | `kutub12345` |

### Telegram bot va testlarni yoqish

Sozlamalar bo'limini (`/sozlamalar/`) bir marta ochib, quyidagilarni to'ldiring:
`telegram_bot_token`, `telegram_admin_chat_id`, `ai_api_key`, `site_base_url`.

```bash
python manage.py run_telegram_bot          # botni ishga tushirish (lokal)
python manage.py generate_quiz --issued    # qo'ldagi kitoblarga test tuzish
python manage.py send_due_quizzes          # kunlik vazifa (test yuborish)
```

To'liq yo'riqnoma: **[TESTLAR.md](TESTLAR.md)**

---

## Serverga joylashtirish

To'liq qadamlar: **[DEPLOY.md](DEPLOY.md)**

Qisqacha: repozitoriya Render, Railway yoki oddiy VPS'ga mos. Serverda bot
**webhook** rejimida ishlaydi — alohida doimiy jarayon kerak emas:

```bash
python manage.py set_telegram_webhook
```

Kunlik vazifa tashqi rejalashtiruvchi orqali maxfiy manzilga murojaat qilish
bilan ishga tushadi (`/testlar/cron/<secret>/`) yoki serverning o'z cron'i bilan.

---

## Kitobxon ilovasi (PWA)

Kitobxon telefonida saytni ochib **«Bosh ekranga qo'shish»** (Android'da avtomatik
taklif chiqadi) orqali ilova sifatida o'rnatadi. Ilova:

- qo'lidagi kitoblar va qaytarish muddatlarini ko'rsatadi
- ochiq testlarni ro'yxatlaydi va yechish imkonini beradi
- telefon raqam + Telegramga keladigan kod bilan kiradi (parol kerak emas)
- internet yo'qolganda ogohlantiradi

---

## Loyiha tuzilishi

```
library_project/
├── manage.py
├── library_project/            # Sozlamalar, asosiy urls.py
├── apps/
│   ├── core/                   # Dashboard, qidiruv, sozlamalar, audit jurnal
│   ├── users/                  # Foydalanuvchilar, rollar, login
│   ├── catalog/                # Mualliflar, toifalar
│   ├── books/                  # Kitoblar, nusxalar
│   ├── readers/                # Kitobxonlar
│   ├── loans/                  # Berish/qaytarish operatsiyalari
│   ├── reports/                # Excel/PDF hisobotlar
│   └── quizzes/                # Testlar, Telegram bot, AI generator
│       ├── models.py           # Quiz, Question, Assignment, Attempt, TelegramAccount
│       ├── bot.py              # Bot mantig'i (polling va webhook uchun umumiy)
│       ├── telegram.py         # Telegram Bot API klienti
│       ├── ai.py               # Savol generatori (Claude / OpenAI)
│       ├── services.py         # Biznes amallari
│       ├── webhooks.py         # Telegram webhook va cron manzillari
│       └── management/commands/
│           ├── generate_quiz.py
│           ├── send_due_quizzes.py
│           ├── run_telegram_bot.py
│           └── set_telegram_webhook.py
├── templates/                  # HTML shablonlar
└── static/                     # CSS, ikonkalar
```

---

## Texnologiyalar

Django 5 · PostgreSQL yoki SQLite · WhiteNoise · Gunicorn · openpyxl · ReportLab

Telegram va AI so'rovlari standart `urllib` orqali yuboriladi — qo'shimcha
kutubxona talab qilinmaydi.

---

## Xavfsizlik haqida

Bu repozitoriya **ochiq**. Quyidagilar hech qachon unga tushmasligi kerak
(`.gitignore` da chiqarib tashlangan):

- `db.sqlite3` — kitobxonlarning ismi, telefon raqami **va bot tokeni** shu yerda
- `.env` — maxfiy kalitlar
- `media/` va `*.xlsx` — yuklangan fayllar, fond jadvallari

Agar token tasodifan GitHub'ga tushib ketsa — BotFather'da `/revoke` qilib
yangi token oling, eskisi bekor bo'ladi.

---

## Litsenziya

MIT — qarang [LICENSE](LICENSE).
