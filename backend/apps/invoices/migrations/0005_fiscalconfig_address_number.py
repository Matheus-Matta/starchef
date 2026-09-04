from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0004_fiscal_profile_shared_by_account"),
    ]

    operations = [
        migrations.AddField(
            model_name="fiscalconfig",
            name="address_number",
            field=models.CharField(
                blank=True,
                help_text="Numero do endereco do emitente.",
                max_length=20,
            ),
        ),
    ]
