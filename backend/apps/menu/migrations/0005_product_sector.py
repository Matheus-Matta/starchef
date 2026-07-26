from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0004_product_requires_variation"),
        ("restaurants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="sector",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="products",
                to="restaurants.tablesector",
            ),
        ),
    ]
