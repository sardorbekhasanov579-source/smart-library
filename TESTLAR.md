# Testlar moduli + Telegram bot (`apps.quizzes`)

Kitobni qaytarish muddati yaqinlashganda kitobxonga shu kitob bo'yicha test
yuboriladi. Belgilangan foizdan yuqori natija — "kitob o'qilgan", past natija
yoki muddat tugashi — "o'qimagan" xabari adminga boradi.

---

## 1. Ishga tushirish (bir martalik)

```bash
# loyiha papkasida
python manage.py makemigrations quizzes
python manage.py migrate
python manage.py runserver
```

So'ng brauzerda **Sozlamalar** bo'limini bir marta ochib chiqing —
yangi sozlamalar avtomatik yaratiladi:
<http://127.0.0.1:8000/sozlamalar/>

### To'ldirilishi kerak sozlamalar

| Kalit | Nima | Misol |
|---|---|---|
| `telegram_bot_token` | BotFather'dan olingan token | `8123456789:AAH...` |
| `telegram_admin_chat_id` | Natija keladigan chat ID(lar), vergul bilan | `123456789` |
| `site_base_url` | Test havolalari uchun manzil | `http://127.0.0.1:8000` |
| `ai_provider` | `anthropic` yoki `openai` | `anthropic` |
| `ai_api_key` | AI kaliti (bo'sh bo'lsa zaxira generator) | `sk-...` |
| `ai_model` | Model nomi (bo'sh — standart) | |
| `quiz_question_count` | Savollar soni | `30` |
| `quiz_pass_percent` | O'tish chegarasi | `70` |
| `quiz_days_before_due` | Muddatdan necha kun oldin yuborilsin | `1` |
| `quiz_show_answers` | Natijadan keyin to'g'ri javoblar ko'rinsinmi | `1` |

> Kalitlarni muhit o'zgaruvchisi orqali ham berish mumkin:
> `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`,
> `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`.
> Sozlamalar sahifasi kalitni ochiq matnda ko'rsatadi — agar bu
> xavfsizlik jihatidan mos bo'lmasa, muhit o'zgaruvchisidan foydalaning.

**Qo'shimcha kutubxona talab qilinmaydi** — Telegram va AI so'rovlari
standart `urllib` orqali yuboriladi.

---

## 2. Telegram botni ishga tushirish

```bash
python manage.py run_telegram_bot
```

Bu oyna ochiq turishi kerak (xabarlarni qabul qilib turadi).

Bot buyruqlari:

| Buyruq | Nima qiladi |
|---|---|
| `/start` | Telefon raqamni so'raydi va kitobxon hisobiga bog'laydi |
| `/testlar` | Ochiq testlar havolasini beradi |
| `/kitoblarim` | Qo'lidagi kitoblar va muddatlar |
| `/id` | Chat ID (admin chat ID ni olish uchun) |
| `/yordam` | Qisqa yo'riqnoma |

**Muhim:** kitobxon botga ulanishi uchun uning telefon raqami kitobxon
kartasida yozilgan bo'lishi kerak (format ahamiyatsiz: `+998901234567`,
`901234567`, `+998 90 123 45 67` — hammasi mos keladi).

Admin chat ID ni olish: botga `/id` yozing, chiqqan raqamni
`telegram_admin_chat_id` sozlamasiga qo'ying.

---

## 3. Savollarni yaratish

Veb orqali: **Testlar → Test to'plamlari** → kitobni qidirib "Test tuzish".

Terminal orqali:

```bash
# bitta kitob
python manage.py generate_quiz --book-id 128

# hozir kitobxonlar qo'lida bo'lgan barcha kitoblar
python manage.py generate_quiz --issued

# muddati ertaga tugaydigan kitoblar
python manage.py generate_quiz --due-in 1

# testi yo'q kitoblardan 50 tasi
python manage.py generate_quiz --all --limit 50

# mavjud testni qayta tuzish
python manage.py generate_quiz --book-id 128 --force
```

### AI kaliti bo'lmasa nima bo'ladi

Savollar kitob kartasidagi ma'lumotlar (nomi, muallifi, toifasi, nashr yili,
nashriyoti, tavsifi) asosida tuziladi. **Bu savollar kitob mazmunini
tekshirmaydi** — faqat kitob haqidagi ma'lumotni. 4267 ta kitobga 30 tadan
mazmunli savol kerak bo'lsa, AI kaliti ulanishi shart.

Savol soni 5 tadan kam bo'lsa test yuborilmaydi — bunday testlar
**Testlar** ro'yxatida sariq nishon bilan ko'rsatiladi, ularni qo'lda
to'ldirish kerak (test sahifasida "Qo'lda savol qo'shish" shakli bor).

---

## 4. Kunlik rejalashtiruvchi

Kuniga bir marta ishga tushishi kerak:

```bash
python manage.py send_due_quizzes
```

Nima qiladi:
1. Qaytarish muddatiga `quiz_days_before_due` kun qolgan, qaytarilmagan
   kitoblarni topadi → test to'plamini oladi (kerak bo'lsa yaratadi) →
   topshiriq biriktiradi → Telegramga havola yuboradi.
2. Muddati o'tib ketgan, ishlanmagan topshiriqlarni yopadi va adminga
   "test ishlanmadi" xabarini yuboradi.

Sinab ko'rish:

```bash
python manage.py send_due_quizzes --dry-run
python manage.py send_due_quizzes --loan-id 15          # bitta operatsiya uchun
python manage.py send_due_quizzes --days 2
python manage.py send_due_quizzes --loan-id 15 --resend # qayta yuborish
```

### Windows Task Scheduler

1. Task Scheduler → **Create Basic Task** → nomi: `Kutubxona testlari`
2. Trigger: **Daily**, masalan 09:00
3. Action: **Start a program**
   - Program: `C:\Users\User\Desktop\smart_library_django\.venv\Scripts\python.exe`
     (virtual muhit bo'lmasa: `python.exe` ning to'liq yo'li)
   - Arguments: `manage.py send_due_quizzes`
   - Start in: `C:\Users\User\Desktop\smart_library_django\library_project`

### Linux cron

```cron
0 9 * * * cd /yo'l/library_project && /yo'l/venv/bin/python manage.py send_due_quizzes >> /var/log/quiz.log 2>&1
```

---

## 5. Kitobxon tomoni

| Sahifa | Manzil |
|---|---|
| Test yechish (Telegramdan kelgan maxfiy havola) | `/testlar/t/<token>/` |
| Natija | `/testlar/t/<token>/natija/` |
| Telefon + Telegram kodi bilan kirish | `/testlar/kirish/` |
| Shaxsiy kabinet (kitoblar + testlar) | `/testlar/kabinet/` |

Test havolasi login talab qilmaydi — token maxfiy, faqat o'sha kitobxonga
Telegram orqali yuboriladi. Kabinetga kirish esa telefon raqam + Telegramga
keladigan 6 xonali kod bilan amalga oshadi (kod 5 daqiqa amal qiladi).

Sahifalar mobil ekran uchun moslashtirilgan — telefonda ilova kabi ishlaydi.

---

## 6. Admin tomoni

| Sahifa | Manzil |
|---|---|
| Test to'plamlari | `/testlar/` |
| Test savollari va sozlamalari | `/testlar/<id>/` |
| Topshiriqlar va natijalar | `/testlar/topshiriqlar/` |
| Bitta topshiriq (havola, urinishlar) | `/testlar/topshiriqlar/<id>/` |
| Urinishdagi javoblar | `/testlar/urinish/<id>/` |
| Telegram va AI holati | `/testlar/telegram/` |

---

## 7. Ish tartibi (to'liq zanjir)

```
Kitob berildi (8 kunga)
        │
        │  7-kuni: python manage.py send_due_quizzes
        ▼
Test to'plami tanlanadi (yoki AI yaratadi)
        │
        ▼
Kitobxonga Telegramda maxfiy havola yuboriladi
        │
        ▼
Kitobxon 30 ta savolga javob beradi
        │
        ├── natija ≥ 70%  →  adminga "✅ Kitob o'qilgan"
        ├── natija < 70%  →  adminga "❌ Kitob o'qilmagan ko'rinadi"
        └── muddat tugadi →  adminga "⌛️ Test ishlanmadi"
```

---

## 8. Yangi jadvallar

| Jadval | Nima saqlanadi |
|---|---|
| `quizzes` | kitob uchun test to'plami |
| `quiz_questions` | savollar |
| `quiz_choices` | javob variantlari |
| `quiz_assignments` | kitobxonga biriktirilgan test (maxfiy token, muddat, holat) |
| `quiz_attempts` | test ishlash urinishi (berilgan savollar, natija) |
| `quiz_answers` | har bir javob |
| `telegram_accounts` | kitobxon ↔ Telegram chat_id bog'lanishi |
| `otp_codes` | bir martalik kirish kodlari |

---

## 9. Tez-tez uchraydigan muammolar

**"Telegram bot tokeni kiritilmagan"** — Sozlamalarda `telegram_bot_token`
bo'sh. BotFather tokenini kiriting.

**Test yuborilmadi: "Telegram ulanmagan"** — kitobxon botga `/start` yuborib,
raqamini tasdiqlamagan. Yoki raqami kitobxon kartasida yo'q. Vaqtinchalik
yechim: topshiriq sahifasidan maxfiy havolani nusxalab, qo'lda bering.

**Savollar mazmunga aloqasi yo'q** — AI kaliti ulanmagan, zaxira generator
ishlagan. `ai_api_key` ni to'ldirib, `--force` bilan qayta tuzing.

**Test havolasi ochilmaydi (telefonda)** — `site_base_url` da `127.0.0.1`
turgan bo'lsa, u faqat serverning o'zida ishlaydi. Telefonda ishlashi uchun
kompyuterning lokal IP manzilini qo'ying (masalan `http://192.168.1.50:8000`)
va serverni `python manage.py runserver 0.0.0.0:8000` bilan ishga tushiring.
`DJANGO_ALLOWED_HOSTS` ga ham shu IP ni qo'shing.
