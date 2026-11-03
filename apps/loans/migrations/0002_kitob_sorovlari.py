# Kitobxonning «kitobni oldim» so'rovlari

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0003_book_location"),
        ("loans", "0001_initial"),
        ("readers", "0002_reader_hemis_id"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BorrowRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Kutilmoqda"),
                            ("approved", "Tasdiqlandi"),
                            ("rejected", "Rad etildi"),
                            ("cancelled", "Bekor qilindi"),
                        ],
                        default="pending",
                        max_length=16,
                        verbose_name="Holat",
                    ),
                ),
                (
                    "reject_reason",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="Rad etish sababi"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="Yuborilgan"
                    ),
                ),
                (
                    "decided_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Ko'rib chiqilgan"
                    ),
                ),
                (
                    "decided_via",
                    models.CharField(
                        blank=True, max_length=16, verbose_name="Qayerdan"
                    ),
                ),
                (
                    "decided_by_name",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Ko'rib chiqqan (Telegram)",
                    ),
                ),
                (
                    "admin_messages",
                    models.JSONField(
                        blank=True, default=list, verbose_name="Admin xabarlari"
                    ),
                ),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="borrow_requests",
                        to="books.book",
                        verbose_name="Kitob",
                    ),
                ),
                (
                    "copy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="borrow_requests",
                        to="books.bookcopy",
                        verbose_name="Nusxa",
                    ),
                ),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="decided_borrow_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Ko'rib chiqqan xodim",
                    ),
                ),
                (
                    "loan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="borrow_requests",
                        to="loans.loan",
                        verbose_name="Berish operatsiyasi",
                    ),
                ),
                (
                    "reader",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="borrow_requests",
                        to="readers.reader",
                        verbose_name="Kitobxon",
                    ),
                ),
            ],
            options={
                "verbose_name": "Kitob olish so'rovi",
                "verbose_name_plural": "Kitob olish so'rovlari",
                "db_table": "borrow_requests",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["status"], name="borrow_requ_status_b066bd_idx"
                    )
                ],
            },
        ),
    ]
