from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0012_caixa_margem_de_fechamento"),
    ]

    operations = [
        migrations.AddField(
            model_name="restaurant",
            name="auto_print_receipt",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="print_cancellation_receipt",
            field=models.BooleanField(default=False),
        ),
    ]
