from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0004_kitchen_dispatch_grace_period")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="fiscal_customer_cpf",
            field=models.CharField(blank=True, default="", max_length=11),
        ),
    ]
