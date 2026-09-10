from pathlib import Path

from django.db import migrations


def _create_image(Image, instance, file_field):
    if not file_field or not file_field.name:
        return None
    return Image.objects.create(
        account_id=instance.account_id,
        file=file_field.name,
        original_name=Path(file_field.name).name[:255],
        content_type="",
        size=0,
        width=0,
        height=0,
        checksum="",
        created_by_id=instance.created_by_id,
        updated_by_id=instance.updated_by_id,
    )


def import_legacy_images(apps, schema_editor):
    Image = apps.get_model("images", "Image")
    ProductImage = apps.get_model("images", "ProductImage")
    Product = apps.get_model("menu", "Product")
    Restaurant = apps.get_model("restaurants", "Restaurant")

    for restaurant in Restaurant.objects.exclude(logo="").filter(logo_image__isnull=True):
        image = _create_image(Image, restaurant, restaurant.logo)
        if image:
            Restaurant.objects.filter(pk=restaurant.pk).update(logo_image=image)

    for product in Product.objects.exclude(image="").filter(logo_image__isnull=True):
        image = _create_image(Image, product, product.image)
        if not image:
            continue
        Product.objects.filter(pk=product.pk).update(logo_image=image)
        ProductImage.objects.create(
            account_id=product.account_id,
            product_id=product.pk,
            image=image,
            position=0,
            created_by_id=product.created_by_id,
            updated_by_id=product.updated_by_id,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("images", "0001_initial"),
        ("menu", "0007_product_logo_image_productcategory_logo_image_and_more"),
        ("restaurants", "0005_restaurant_logo_image"),
    ]

    operations = [migrations.RunPython(import_legacy_images, migrations.RunPython.noop)]
