# Kitobxon o'zi: bot orqali ro'yxatdan o'tish, AI tahlili, bazadagi kesh jadvali

import django.utils.timezone
from django.db import migrations, models


def create_cache_table(apps, schema_editor):
    """settings.CACHES dagi bazaviy kesh jadvali (django_cache)."""
    from django.core.management import call_command

    call_command("createcachetable", verbosity=0)


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0002_telegramaccount_notifications_enabled"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramRegistration",
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
                    "chat_id",
                    models.BigIntegerField(
                        unique=True, verbose_name="Telegram chat ID"
                    ),
                ),
                ("phone", models.CharField(max_length=32, verbose_name="Telefon")),
                (
                    "step",
                    models.CharField(
                        default="name", max_length=16, verbose_name="Qadam"
                    ),
                ),
                (
                    "full_name",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="F.I.Sh."
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        blank=True, max_length=64, verbose_name="Telegram username"
                    ),
                ),
                (
                    "first_name",
                    models.CharField(blank=True, max_length=100, verbose_name="Ism"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="Boshlangan"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Yangilangan"),
                ),
            ],
            options={
                "verbose_name": "Bot orqali ro'yxatdan o'tish",
                "verbose_name_plural": "Bot orqali ro'yxatdan o'tishlar",
                "db_table": "telegram_registrations",
            },
        ),
        migrations.AddField(
            model_name="attempt",
            name="ai_feedback",
            field=models.JSONField(blank=True, default=dict, verbose_name="AI tahlili"),
        ),
        migrations.RunPython(create_cache_table, migrations.RunPython.noop),
    ]
