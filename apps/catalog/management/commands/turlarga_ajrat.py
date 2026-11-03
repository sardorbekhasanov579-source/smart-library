"""Guruhsiz toifalarni kitob turlari bo'yicha guruhlarga joylaydi.

Yangi fond yuklangandan keyin yoki qo'lda yangi toifa qo'shilganda ishlatiladi
(Excel orqali qo'shishda bu avtomatik bajariladi):

    python manage.py turlarga_ajrat
"""
from django.core.management.base import BaseCommand

from apps.catalog.kinds import GROUP_NAMES, assign_groups


class Command(BaseCommand):
    help = "Toifalarni Badiiy / O'quv / Ilmiy ... guruhlariga ajratadi"

    def handle(self, *args, **options):
        moved = assign_groups()
        self.stdout.write(self.style.SUCCESS(f"{moved} ta toifa guruhlarga joylandi."))
        self.stdout.write("Guruhlar: " + ", ".join(GROUP_NAMES))
