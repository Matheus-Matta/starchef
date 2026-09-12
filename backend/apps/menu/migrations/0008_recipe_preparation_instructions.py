from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0007_product_logo_image_productcategory_logo_image_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipe",
            name="preparation_instructions",
            field=models.TextField(blank=True, default=""),
        ),
    ]
