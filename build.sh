#!/usr/bin/env bash
# Render (va shunga o'xshash xizmatlar) har joylashtirishda shu faylni ishga tushiradi.
set -o errexit

echo "--> Kutubxonalar o'rnatilmoqda"
pip install --upgrade pip
pip install -r requirements.txt

echo "--> Statik fayllar yig'ilmoqda"
python manage.py collectstatic --no-input

echo "--> Baza migratsiyalari"
python manage.py migrate --no-input

echo "--> Administrator tekshirilmoqda"
python manage.py ensure_admin

echo "--> Tayyor"
