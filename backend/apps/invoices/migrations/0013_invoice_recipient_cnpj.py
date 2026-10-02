from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("invoices", "0012_unico_so_entre_ativos"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="recipient_cnpj",
            field=models.CharField(blank=True, max_length=18),
        ),
    ]
