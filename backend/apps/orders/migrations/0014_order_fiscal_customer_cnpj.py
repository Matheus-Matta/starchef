from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0013_campos_adicionais_e_codigo_do_operador"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="fiscal_customer_cnpj",
            field=models.CharField(blank=True, default="", max_length=14),
        ),
    ]
