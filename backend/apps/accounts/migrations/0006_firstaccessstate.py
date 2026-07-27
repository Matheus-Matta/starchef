from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_account_max_restaurants_account_max_users"),
    ]

    operations = [
        migrations.CreateModel(
            name="FirstAccessState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("singleton", models.BooleanField(default=True, editable=False, unique=True)),
                ("completed_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ],
            options={
                "verbose_name": "estado do primeiro acesso",
                "verbose_name_plural": "estado do primeiro acesso",
            },
        ),
    ]
