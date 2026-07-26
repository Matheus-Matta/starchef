from django.db import migrations, models


def migrate_required_variations(apps, schema_editor):
    Product = apps.get_model("menu", "Product")
    ProductVariation = apps.get_model("menu", "ProductVariation")
    product_ids = ProductVariation.objects.filter(is_required=True).values_list("product_id", flat=True).distinct()
    Product.objects.filter(id__in=product_ids).update(requires_variation=True)


class Migration(migrations.Migration):
    dependencies = [("menu", "0003_alter_ingredient_restaurant")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="requires_variation",
            field=models.BooleanField(
                default=False,
                help_text="Exige que o operador escolha uma das variacoes ativas antes de adicionar o produto ao pedido.",
            ),
        ),
        migrations.RunPython(migrate_required_variations, migrations.RunPython.noop),
        migrations.RemoveField(model_name="productvariation", name="is_required"),
    ]
