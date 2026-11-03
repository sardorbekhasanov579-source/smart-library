# Kitob joylashuvi: Xona -> Javon -> Taxcha

from django.db import migrations, models


def parse_existing(apps, schema_editor):
    """Avval yozilgan javon matnlaridan xona/javon/taxchani ajratib oladi."""
    from apps.books.location import format_location, parse_location

    Book = apps.get_model("books", "Book")
    for book in Book.objects.exclude(shelf_location="").only("id", "shelf_location"):
        parsed = parse_location(book.shelf_location)
        if not parsed:
            continue
        Book.objects.filter(pk=book.pk).update(
            room=parsed["room"],
            shelf=parsed["shelf"],
            tier=parsed["tier"],
            shelf_location=format_location(
                parsed["room"], parsed["shelf"], parsed["tier"]
            )[:50],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0002_book_price"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="book",
            name="room",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Xona"
            ),
        ),
        migrations.AddField(
            model_name="book",
            name="shelf",
            field=models.CharField(
                blank=True,
                help_text="Qator harfi bilan: 1A, 2A ... 1B, 2B",
                max_length=8,
                verbose_name="Javon",
            ),
        ),
        migrations.AddField(
            model_name="book",
            name="tier",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Taxcha"
            ),
        ),
        migrations.AddIndex(
            model_name="book",
            index=models.Index(fields=["room", "shelf"], name="books_room_e87abb_idx"),
        ),
        migrations.RunPython(parse_existing, migrations.RunPython.noop),
    ]
