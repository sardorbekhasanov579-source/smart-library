# Smart Library Android API — 1-bosqich

Bu o'zgarishlar mavjud Django loyihasiga Android uchun API qatlamini qo'shadi. Mavjud modellarni o'zgartirmaydi va yangi DB migratsiyasi talab qilmaydi.

## Fayllar
- `apps/mobile_api/` — login, profil, kitoblar, ijtimoiy faollik, reyting va test endpointlari.
- `requirements.txt` — Django REST Framework va SimpleJWT kutubxonalari qo'shilgan.
- `library_project/settings.py` — REST Framework/JWT sozlamalari.
- `library_project/urls.py` — `/api/v1/` yo'li.

## O'rnatish
Loyiha papkasida terminal ochib:

```bash
pip install -r requirements.txt
python manage.py check
```

Keyin lokalda:

```bash
python manage.py runserver
```

Render ishlatilsa, o'zgarishlarni GitHub'ga push qiling. Render `requirements.txt` orqali kutubxonalarni o'rnatishi kerak.

## API endpointlar
- `POST /api/v1/auth/login/` — `{"username":"...","password":"..."}`; access/refresh token qaytaradi.
- `POST /api/v1/auth/refresh/` — `{"refresh":"..."}`.
- `GET /api/v1/me/` — profil, faol kitoblar soni, ijtimoiy ball va umumiy reyting o'rni.
- `GET /api/v1/me/loans/` — kitobxonning kitob olish/qaytarish tarixi.
- `GET /api/v1/me/social-activity/` — ballar va faollik tarixi.
- `GET /api/v1/social-activity/leaderboard/?period=all|month|year` — reyting.
- `GET /api/v1/books/?q=...&available=1&page=1` — kitob qidirish.
- `GET /api/v1/books/{id}/` — kitob tafsiloti va nusxalarning javon joylashuvi.
- `GET /api/v1/tests/assignments/` — kitobxonga biriktirilgan testlar.
- `POST /api/v1/tests/assignments/{id}/start/` — test urinishini boshlash/savollarni olish.
- `POST /api/v1/tests/attempts/{id}/submit/` — javoblarni topshirish. Body misoli: `{"answers":{"12":45,"13":48}}`.

Himoyalangan endpointlarga quyidagi header qo'shiladi:

```http
Authorization: Bearer ACCESS_TOKEN
```

## Muhim shartlar
1. Kitobxon mobil ilovaga kirishi uchun `users.User` hisobining `role=reader` bo'lishi va u `readers.Reader.user` bilan bog'langan bo'lishi kerak.
2. Android ichiga Gemini yoki boshqa AI maxfiy API kalitlari joylanmaydi.
3. Test javoblarining to'g'riligi API javobida oshkor qilinmaydi; baholash serverda bajariladi.
4. Hozirgi bosqichda testning muddati mavjud `Assignment.deadline` bilan nazorat qilinadi. Telefon boshqa ilovaga o'tganini qayd etish, autosave va qat'iy imtihon sessiyasi keyingi bosqichda qo'shiladi.
5. Bu muhitda Django o'rnatilmaganligi sabab `manage.py check` ishga tushmadi. Python fayllari sintaksis bo'yicha compile tekshiruvidan o'tdi; ishchi loyihada `pip install -r requirements.txt` dan keyin albatta `python manage.py check` bajaring.
