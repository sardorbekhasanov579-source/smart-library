from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramaccount",
            name="notifications_enabled",
            field=models.BooleanField(
                default=True,
                help_text="O'chirilsa, test va eslatma xabarlari Telegramga "
                "yuborilmaydi (kirish kodi baribir yuboriladi).",
                verbose_name="Bildirishnomalar yoqilgan",
            ),
        ),
    ]
