"""Acervo de imagens e os vinculos ordenados com produtos."""
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TenantBaseModel


def image_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"accounts/{instance.account_id}/images/{instance.id}{suffix}"


class Image(TenantBaseModel):
    """Arquivo validado uma vez e reutilizavel por entidades da mesma conta."""

    file = models.ImageField(upload_to=image_upload_path, max_length=400)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, db_index=True)
    alt_text = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["account", "checksum"])]

    def __str__(self):
        return self.original_name

    @property
    def url(self):
        try:
            return self.file.url
        except ValueError:
            return ""

    def public_url(self, request=None):
        url = self.url
        if not url or request is None or url.startswith(("http://", "https://")):
            return url
        return request.build_absolute_uri(url)

    @classmethod
    def create_from_upload(cls, uploaded, *, account, user=None, alt_text=""):
        from apps.images.validation import validate_image_upload

        metadata = getattr(uploaded, "_starchef_image_metadata", None)
        metadata = metadata or validate_image_upload(uploaded)
        return cls.objects.create(
            account=account,
            file=uploaded,
            alt_text=alt_text,
            created_by=user,
            updated_by=user,
            **metadata,
        )


class ProductImage(TenantBaseModel):
    """Posicao de uma imagem na galeria (`photo_list`) de um produto."""

    product = models.ForeignKey(
        "menu.Product", related_name="product_images", on_delete=models.CASCADE
    )
    image = models.ForeignKey(
        Image, related_name="product_links", on_delete=models.PROTECT
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "image"], name="unique_image_in_product_gallery"
            )
        ]

    def clean(self):
        if self.product_id and self.image_id:
            if self.product.account_id != self.image.account_id:
                raise ValidationError("A imagem e o produto devem pertencer a mesma conta.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
