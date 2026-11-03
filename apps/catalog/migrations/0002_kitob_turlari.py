"""Mayda toifalarni kitob turlari bo'yicha guruhlarga ajratish.

Badiiy adabiyot, O'quv adabiyoti, Ilmiy adabiyot, Ijtimoiy-siyosiy,
Lug'at va ma'lumotnoma, Boshqa. Mavjud toifalar o'chirilmaydi — faqat
mos guruh ichiga ko'chiriladi. Kitoblarning toifasi o'zgarmaydi.
"""
from django.db import migrations


def group_categories(apps, schema_editor):
    from apps.catalog.kinds import assign_groups

    Category = apps.get_model("catalog", "Category")
    assign_groups(Category=Category)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
        ("books", "0003_book_location"),
    ]

    operations = [
        migrations.RunPython(group_categories, migrations.RunPython.noop),
    ]
