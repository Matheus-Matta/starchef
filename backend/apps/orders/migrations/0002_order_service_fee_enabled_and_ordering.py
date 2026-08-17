from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="service_fee_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterModelOptions(
            name="order",
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(
                fields=["restaurant", "updated_at"],
                name="orders_rest_updated_idx",
            ),
        ),
    ]
