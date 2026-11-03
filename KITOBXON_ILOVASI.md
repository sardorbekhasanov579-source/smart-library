# Kitobxon ilovasi — 4 bo'lim

Kitobxon telefon raqami + Telegramdan kelgan kod bilan kiradi:
`/testlar/kirish/`. Kirgandan keyin pastda 4 ta bo'lim paydo bo'ladi.

| Bo'lim | Manzil | Nimalar bor |
|---|---|---|
| Mening sahifam | `/testlar/kabinet/` | F.I.Sh., kitobxon kodi, HEMIS ID, telefon, turi; qo'lidagi kitoblar muddat chizig'i va javon manzili bilan; faollik balli va reytingdagi o'rni; ogohlantirishlar |
| Kitoblar bazasi | `/testlar/kabinet/kitoblar/` | Fondni qidirish (nom, muallif, toifa, ISBN, inventar raqam); kitobni bosganda nusxalar ro'yxati — qaysi javonda turgani va holati |
| Testlarim | `/testlar/kabinet/testlar/` | Faol / yakunlangan / hammasi; muddat, natija foizi, «Testni boshlash» tugmasi |
| Sozlamalar | `/testlar/kabinet/sozlamalar/` | Telegram holati va bildirishnomalar, mavzu (yorqin/tungi/tizim), matn kattaligi, ilovani o'rnatish, kutubxona telefoni va qoidalari, hisobdan chiqish |

## Shu o'zgarish bilan qo'shilgani

**Bildirishnomalar o'chirgichi.** `telegram_accounts` jadvaliga
`notifications_enabled` maydoni qo'shildi. Kitobxon o'chirib qo'ysa, test va
eslatma xabarlari Telegramga yuborilmaydi (test kabinetda baribir ko'rinadi).
Kirish kodi esa har holda yuboriladi.

**Ikki yangi sozlama.** `/sozlamalar/` bo'limida o'zi paydo bo'ladi:

- `library_phone` — kitobxon ilovasidagi «Kutubxonaga qo'ng'iroq» tugmasi
- `library_hours` — ish vaqti (masalan: `Du-Sha 9:00-18:00`)

**Mavzu va matn kattaligi** faqat o'sha telefonda saqlanadi (localStorage),
serverga yozilmaydi.

## Javon manzilini to'ldirish

Hozir bazadagi **4138 kitob va 4267 nusxaning hammasida javon manzili bo'sh**,
shuning uchun kitoblar bazasida «javon ko'rsatilmagan» deb turadi. To'ldirish
uchun Excel fayl tayyorlang:

| inventar | javon |
|---|---|
| 000123 | A-12-3 |
| 000124 | A-12-4 |

yoki inventar raqam o'rniga kitob nomi bilan:

| kitob nomi | javon |
|---|---|
| Fizika asoslari | B-04-1 |

Keyin:

```
python manage.py javon_yuklash javonlar.xlsx --quruq   # sinab ko'rish
python manage.py javon_yuklash javonlar.xlsx           # haqiqiy yuklash
```

Sarlavha nomlari erkin: ustun nomida «inventar», «kitob» yoki «javon» so'zi
bo'lsa yetarli. `--quruq` bilan ishga tushirilganda bazaga hech narsa
yozilmaydi, faqat nima bo'lishini ko'rsatadi.

Bitta-bitta tahrirlash ham mumkin: kitob kartasi va nusxa kartasidagi
«Javon manzili» maydoni.

## O'rnatish qadamlari

```
python manage.py migrate
python manage.py collectstatic --noinput    # faqat serverda
```

Lokal sinab ko'rish: `python manage.py runserver`, so'ng telefon yoki
brauzerda `/testlar/kirish/`.

---

# Kitobxon darajalari

Faollik ballari asosida kitobxonga daraja beriladi. Daraja bazada saqlanmaydi —
ball o'zgarishi bilan o'zi qayta hisoblanadi, hech qanday migratsiya kerak emas.

| Daraja | Kerakli ball | Imtiyoz (standartga qo'shiladi) |
|---|---|---|
| Yangi kitobxon | 0 | — |
| Faol kitobxon | 20 | +1 kitob, +3 kun |
| Bilimdon | 60 | +2 kitob, +7 kun |
| Oltin kitobxon | 120 | +3 kitob, +14 kun |

Ya'ni standart 5 kitob / 14 kun bo'lsa, «Bilimdon» 7 ta kitobni 21 kunga oladi.
Imtiyoz **qo'shiladi**, hech kimning hozirgi huquqi kamaymaydi.

Daraja ikki joyda ishlaydi:

- `Reader.can_borrow` — limit `Reader.book_limit` dan olinadi
- `Loan.issue()` — muddat `Reader.loan_days` dan olinadi

Ko'rinadigan joylari: kitobxon ilovasining bosh sahifasi (daraja va keyingi
darajagacha qolgan ball), Sozlamalar → «Mening darajam» (to'liq jadval),
kutubxonachi uchun Faollik reytingida «Daraja» ustuni.

## Sozlash

`/sozlamalar/` bo'limida beshta kalit o'zi paydo bo'ladi:

| Kalit | Standart | Ma'nosi |
|---|---|---|
| `level_faol_min` | 20 | «Faol kitobxon» uchun ball |
| `level_bilimdon_min` | 60 | «Bilimdon» uchun ball |
| `level_oltin_min` | 120 | «Oltin kitobxon» uchun ball |
| `level_bonus_books` | 1,2,3 | Uch daraja uchun qo'shimcha kitob |
| `level_bonus_days` | 3,7,14 | Uch daraja uchun qo'shimcha kun |

Oxirgi ikkitasi vergul bilan ajratilgan uchta son: Faol, Bilimdon, Oltin
tartibida. Noto'g'ri yozilsa tizim 0 deb oladi va yiqilmaydi.

---

# Yangi imkoniyatlar (oktyabr 2026)

## Kitob joyi: Xona → Javon → Taxcha
Har bir kitobda uchta maydon bor: **Xona** (1, 2, 3), **Javon** (1A, 2A … 1B, 2B — har xonada
1A dan boshlanadi), **Taxcha** (1, 2, 3 …). Ilovada «2-xona · 1A · 3-taxcha» ko'rinishida chiqadi.

- Admin panel → **Javonlar**: har xona bo'yicha qatorlar va javonlar, javonni bossangiz taxchalar bo'yicha kitoblar.
- Excel'dan yuklash: Kitoblar → «Exseldan qo'shish» → **«Mavjud kitoblarga joylashuv yozish»**.
  Ustunlar: `Xona | Javon | Taxcha | Kitob nomi | Muallif` (yoki `Inventar` raqami). Avval tahlil
  ko'rsatiladi (topilgan / topilmagan kitoblar), tasdiqlagach yoziladi.

## Kitob turlari
Fonddagi ~30 mayda toifa 6 guruhga ajratildi: Badiiy, O'quv, Ilmiy, Ijtimoiy-siyosiy,
Lug'at va ma'lumotnoma, Boshqa. Ilovaning «Kitoblar» bo'limida tugmalar bilan tanlanadi.
Yangi toifalar Excel orqali qo'shilganda o'zi guruhlanadi. Qo'lda: `python manage.py turlarga_ajrat`.

## Bot orqali ro'yxatdan o'tish
Bazada yo'q odam botga /start → raqamini yuboradi → F.I.Sh. va turini tanlaydi → kitobxon
yaratiladi, adminga xabar keladi. Botdagi **«📱 Kabinet»** tugmasi ilovaga parolsiz kiritadi (1 soat amal qiladi).

## «Shu kitobni oldim» → admin tasdig'i
Kitobxon ilovada kitobni belgilaydi → adminlarga Telegram'da **✅ Tasdiqlash / ❌ Rad etish** tugmalari
bilan xabar keladi (yoki panel → **Kitob so'rovlari**). Tasdiqlansa haqiqiy berish operatsiyasi
yoziladi va kitobxonga xabar boradi.

## Test va AI tahlil
Kitobxon «Testlarim» bo'limida olgan kitobini tanlab testni o'zi boshlaydi (test bo'lmasa AI fonda tuzadi).
Natija adminga Telegram'da keladi; kitobxon o'tdi/o'tmadi ko'radi, xato qilgan bo'lsa AI qaysi
mavzularni qayta o'qish kerakligini aytadi (sahifada va Telegramda). 2 ta urinish beriladi
(`quiz_self_attempts` sozlamasi).
