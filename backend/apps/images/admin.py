from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.images.models import Image, ProductImage


@admin.register(Image)
class ImageAdmin(TenantModelAdmin):
    list_display = ("original_name", "account", "content_type", "size", "width", "height")
    search_fields = ("original_name", "checksum")
    list_filter = ("account", "content_type")


@admin.register(ProductImage)
class ProductImageAdmin(TenantModelAdmin):
    list_display = ("product", "image", "position", "account")
    list_filter = ("account",)
