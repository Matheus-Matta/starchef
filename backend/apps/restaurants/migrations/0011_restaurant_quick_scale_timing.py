from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0010_unico_so_entre_ativos"),
    ]

    operations = [
        migrations.AddField(
            model_name="restaurant",
            name="quick_scale_command_timeout_seconds",
            field=models.PositiveIntegerField(default=45),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="quick_scale_stability_seconds",
            field=models.PositiveIntegerField(default=3),
        ),
    ]
