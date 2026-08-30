from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("invoices", "0005_fiscalconfig_address_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="fiscalconfig",
            name="district",
            field=models.CharField(
                blank=True,
                help_text="Bairro do endereco do emitente.",
                max_length=120,
            ),
        ),
    ]
