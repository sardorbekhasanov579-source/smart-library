# GitHub'ga joylash va serverga chiqarish

Ikki qism: avval kod GitHub'ga, keyin server. Hammasi ketma-ket, qadam-baqadam.

---

## 0-qism. Nima uchun aynan shunday

**Hosting tanlovi — Render (bepul).** Sababi: GitHub bilan bog'lanadi
(`git push` → avtomatik yangilanadi), PostgreSQL beradi, tarmoqqa cheklov yo'q
(Telegram API ishlaydi), kartasiz boshlash mumkin.

Bepul tarifning ikkita kamchiligi bor, ikkalasini ham hal qilamiz:

| Kamchilik | Yechim |
|---|---|
| 15 daqiqa harakatsizlikdan keyin server "uxlaydi", birinchi ochilish ~1 daqiqa | Bepulda chidasa bo'ladi. $7/oy bilan yo'qoladi |
| Bepul PostgreSQL **30 kundan keyin o'chadi** | Yoki $7/oy to'lanadi, yoki bepul **Neon** bazasidan foydalaniladi (muddatsiz) |
| Doimiy ishlaydigan bot jarayoni yo'q | Bot **webhook** rejimida ishlaydi — alohida jarayon kerak emas |
| Cron (kunlik vazifa) pullik | Tashqi bepul **cron-job.org** maxfiy manzilga murojaat qiladi |

Ya'ni to'liq bepul ishlaydigan tizim chiqadi.

---

## 1-qism. GitHub

### 1.1. Git o'rnatilganini tekshiring

```bash
git --version
```

Xato bersa <https://git-scm.com/download/win> dan o'rnating.

### 1.2. Repozitoriyani tayyorlang

```bash
cd C:\Users\User\Desktop\smart_library_django\library_project

git init
git branch -M main
git add .
git status
```

**⚠️ `git status` natijasini diqqat bilan o'qing.** Quyidagilar ro'yxatda
**BO'LMASLIGI** kerak:

- `db.sqlite3` — bunda kitobxonlarning telefon raqamlari **va bot tokeningiz** bor
- `.env`
- `umumiy fond.xlsx`
- `media/`

Agar ular ko'rinsa — to'xtang, `.gitignore` ishlamayapti, menga ayting.

### 1.3. Birinchi commit

```bash
git config user.name "Ism Familiya"
git config user.email "sizning@email.com"

git commit -m "Smart Library: kutubxona tizimi, testlar moduli va Telegram bot"
```

### 1.4. GitHub'da repozitoriya yarating

1. <https://github.com/new> ga kiring
2. **Repository name**: `smart-library`
3. **Public** ni tanlang
4. **README, .gitignore, license qo'shmang** — bizda allaqachon bor
5. **Create repository**

### 1.5. Yuklang

GitHub ko'rsatgan manzilni ishlating:

```bash
git remote add origin https://github.com/FOYDALANUVCHI/smart-library.git
git push -u origin main
```

Parol so'ralsa — GitHub paroli emas, **Personal Access Token** kerak:
Settings → Developer settings → Personal access tokens → Tokens (classic) →
Generate new token → `repo` ruxsatini belgilang.

Keyingi o'zgarishlarni yuborish:

```bash
git add .
git commit -m "nima o'zgardi"
git push
```

---

## 2-qism. Ma'lumotlar bazasi (Neon — bepul, muddatsiz)

Render'ning bepul bazasi 30 kundan keyin o'chadi, shuning uchun Neon ishlatamiz.

1. <https://neon.tech> → GitHub bilan ro'yxatdan o'ting
2. **Create project** → nom: `smart-library`, region: **Europe (Frankfurt)**
3. Chiqqan **Connection string** ni nusxa oling, shunga o'xshash bo'ladi:

```
postgresql://foydalanuvchi:parol@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

Buni saqlab qo'ying — keyingi qadamda kerak bo'ladi.

---

## 3-qism. Render

### 3.1. Xizmatni yarating

1. <https://render.com> → GitHub bilan kiring
2. **New +** → **Web Service** → repozitoriyangizni tanlang
3. Sozlamalar:

| Maydon | Qiymat |
|---|---|
| Name | `smart-library` |
| Region | Frankfurt |
| Branch | `main` |
| Root Directory | *(bo'sh qoldiring)* |
| Runtime | Python 3 |
| Build Command | `chmod +x build.sh && ./build.sh` |
| Start Command | `gunicorn library_project.wsgi:application --workers 2 --timeout 120` |
| Instance Type | Free |

### 3.2. Muhit o'zgaruvchilari (Environment Variables)

**Advanced → Add Environment Variable** orqali qo'shasiz:

| Nomi | Qiymati |
|---|---|
| `PYTHON_VERSION` | `3.12.7` |
| `DJANGO_SECRET_KEY` | uzun tasodifiy matn (pastda yaratish usuli) |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_SSL_REDIRECT` | `1` |
| `DATABASE_URL` | Neon'dan olgan manzil |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | kuchli parol o'ylab toping |
| `TELEGRAM_BOT_TOKEN` | BotFather tokeni |
| `TELEGRAM_ADMIN_CHAT_ID` | o'z chat ID ingiz |
| `ANTHROPIC_API_KEY` | AI kaliti (bo'lsa) |

`DJANGO_SECRET_KEY` yaratish:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 3.3. Deploy

**Create Web Service** bosasiz. 3–5 daqiqada `https://smart-library-xxxx.onrender.com`
manzili tayyor bo'ladi. Build jurnalida xato chiqsa — matnini menga tashlang.

Sayt ochilgach `ADMIN_USERNAME` / `ADMIN_PASSWORD` bilan kirasiz va
**darhol parolni o'zgartirasiz** (Profil → Parolni o'zgartirish).

---

## 4-qism. Ma'lumotlarni ko'chirish (4267 ta kitob)

Lokal bazadagi ma'lumotlarni serverga ko'chirish.

**Lokal kompyuterda:**

```bash
python manage.py dumpdata ^
  --natural-foreign --natural-primary ^
  --exclude contenttypes --exclude auth.Permission ^
  --exclude sessions --exclude admin.logentry ^
  --indent 2 -o malumotlar.json
```

(Linux/Mac'da `^` o'rniga `\`)

`malumotlar.json` hajmi katta bo'ladi — uni **GitHub'ga yuklamang**
(`.gitignore` da `*.json` yo'q, shuning uchun qo'lda ehtiyot bo'ling).

**Serverga yuklash** uchun Render'da Shell kerak (bepul tarifda yo'q).
Shuning uchun eng oson yo'l — lokal kompyuterdan to'g'ridan-to'g'ri
Neon bazasiga yozish:

```bash
# Windows'da vaqtincha DATABASE_URL ni o'rnatib
set DATABASE_URL=postgresql://...neon...?sslmode=require
set DJANGO_DEBUG=0
set DJANGO_ALLOWED_HOSTS=*

python manage.py migrate
python manage.py loaddata malumotlar.json
```

Shundan keyin `set DATABASE_URL=` deb bo'shatasiz — lokal ish yana SQLite'ga qaytadi.

---

## 5-qism. Telegram botni webhook'ga o'tkazish

Serverda bot alohida jarayon sifatida emas, webhook orqali ishlaydi.

**1.** Sayt manzilini sozlamalarga yozasiz: saytga kirib `/sozlamalar/` →
`site_base_url` = `https://smart-library-xxxx.onrender.com`

**2.** Webhookni o'rnatasiz. Lokal kompyuterdan Neon bazasiga ulangan holda:

```bash
set DATABASE_URL=postgresql://...neon...?sslmode=require
python manage.py set_telegram_webhook
```

Yoki Render'da Shell bo'lsa — o'sha yerdan.

**3.** Tekshirasiz:

```bash
python manage.py set_telegram_webhook --info
```

`URL:` qatorida sayt manzilingiz turishi kerak, `Oxirgi xato` bo'lmasligi kerak.

Endi botga Telegramda `/start` yozsangiz — server javob beradi, kompyuteringiz
o'chiq bo'lsa ham.

> **Eslatma:** bepul tarifda server uxlab qolsa, birinchi xabarga javob ~1 daqiqa
> kechikadi. Telegram xabarni qayta yuboradi, shuning uchun yo'qolmaydi.

---

## 6-qism. Kunlik vazifa (testlarni yuborish)

**1.** Maxfiy manzilni olasiz. Saytga admin sifatida kirib `/sozlamalar/` ni oching —
`cron_secret` qiymatini nusxa oling (birinchi marta bo'sh bo'lsa, quyidagi
manzilni bir marta ochganda avtomatik yaratiladi).

Manzil shunday ko'rinishda bo'ladi:

```
https://smart-library-xxxx.onrender.com/testlar/cron/MAXFIY_KALIT/
```

**2.** <https://cron-job.org> da bepul ro'yxatdan o'tasiz:

- **Create cronjob**
- **URL**: yuqoridagi manzil
- **Schedule**: Every day, soat `09:00`
- **Timezone**: Asia/Tashkent
- **Create**

Har kuni ertalab bu manzil ochiladi, server muddati yaqinlashgan kitoblar
bo'yicha testlarni yuboradi va muddati o'tganlarni yopadi.

**3.** Sinab ko'rish: manzilni brauzerda oching. `{"ok": true, ...}` chiqishi kerak.

---

## 7-qism. Kitobxon ilovasini o'rnatish (PWA)

Kitobxon telefonida saytni ochadi:

```
https://smart-library-xxxx.onrender.com/testlar/kirish/
```

- **Android (Chrome):** pastda «Ilovani o'rnating» tasmasi chiqadi → **O'rnatish**
- **iPhone (Safari):** pastdagi «Ulashish» belgisi → **«Bosh ekranga qo'shish»**

Ilova bosh ekranda kitob belgisi bilan paydo bo'ladi, brauzer manzil qatorisiz
to'liq ekranda ochiladi.

---

## Tekshiruv ro'yxati

- [ ] `git status` da `db.sqlite3` va `.env` yo'q
- [ ] GitHub'da repozitoriya ochildi
- [ ] Render'da sayt ochildi va kirish ishlaydi
- [ ] Admin paroli o'zgartirildi
- [ ] Ma'lumotlar ko'chirildi (kitoblar ko'rinyapti)
- [ ] `site_base_url` serverning HTTPS manzili
- [ ] Webhook o'rnatildi, botga `/start` javob beryapti
- [ ] Cron manzili cron-job.org ga qo'shildi
- [ ] Telefonda ilova o'rnatildi

---

## Agar token GitHub'ga tushib ketsa

1. BotFather'ga `/revoke` yuborasiz → eski token bekor bo'ladi
2. Yangi token olasiz va Render'dagi `TELEGRAM_BOT_TOKEN` ni yangilaysiz
3. AI kaliti tushgan bo'lsa — provayder panelidan o'chirib, yangisini olasiz

Git tarixidan faylni butunlay o'chirish qiyin, shuning uchun eng ishonchlisi —
kalitni almashtirish.
