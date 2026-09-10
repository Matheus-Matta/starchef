"""Contrato de imagens de produto e variante."""
from django.db import transaction
from rest_framework import serializers

from apps.images.models import Image, ProductImage
from apps.images.serializers import ValidatedImageField, image_data
from apps.images.validation import validate_image_upload


class ProductImagesMixin(serializers.Serializer):
    logo_p = serializers.SerializerMethodField()
    logo_p_id = serializers.UUIDField(source="logo_image_id", read_only=True)
    logo_image = serializers.UUIDField(source="logo_image_id", read_only=True)
    photo_list = serializers.SerializerMethodField()
    logo_p_upload = ValidatedImageField(write_only=True, required=False)
    photo_uploads = serializers.ListField(
        child=ValidatedImageField(), write_only=True, required=False
    )
    photo_remove_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )

    def get_logo_p(self, obj):
        image = obj.logo_image
        if image:
            return image.public_url(self.context.get("request"))
        legacy = getattr(obj, "image", None)
        if not legacy:
            return ""
        try:
            url = legacy.url
        except ValueError:
            return ""
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request and not url.startswith("http") else url

    def get_photo_list(self, obj):
        links = obj.product_images.all()
        return [
            image_data(
                link.image,
                self,
                primary=link.image_id == obj.logo_image_id,
                position=link.position,
            )
            for link in links
        ]

    def _attach(self, product, uploaded, *, primary=False):
        request = self.context.get("request")
        metadata = getattr(uploaded, "_starchef_image_metadata", None)
        metadata = metadata or validate_image_upload(uploaded)
        existing = product.product_images.select_related("image").filter(
            image__checksum=metadata["checksum"]
        ).first()
        if existing:
            if primary or not product.logo_image_id:
                product.logo_image = existing.image
                product.save(update_fields=["logo_image", "updated_at"])
            return
        image = Image.create_from_upload(
            uploaded, account=product.account, user=getattr(request, "user", None)
        )
        position = product.product_images.count()
        ProductImage.objects.create(
            account=product.account,
            product=product,
            image=image,
            position=position,
            created_by=getattr(request, "user", None),
            updated_by=getattr(request, "user", None),
        )
        getattr(product, "_prefetched_objects_cache", {}).pop("product_images", None)
        if primary or not product.logo_image_id:
            product.logo_image = image
            product.save(update_fields=["logo_image", "updated_at"])

    def _save_images(self, product, logo, photos):
        if logo:
            self._attach(product, logo, primary=True)
        for uploaded in photos:
            self._attach(product, uploaded)
        return product

    def _remove_images(self, product, image_ids):
        if not image_ids:
            return product
        links = product.product_images.filter(image_id__in=image_ids)
        linked_ids = set(links.values_list("image_id", flat=True))
        if not linked_ids:
            return product
        product.variations.filter(logo_image_id__in=linked_ids).update(logo_image=None)
        links.delete()
        cache = getattr(product, "_prefetched_objects_cache", {})
        cache.pop("product_images", None)
        cache.pop("variations", None)
        if product.logo_image_id in linked_ids:
            replacement = product.product_images.order_by("position", "created_at").first()
            product.logo_image = replacement.image if replacement else None
            product.save(update_fields=["logo_image", "updated_at"])
        return product

    @transaction.atomic
    def create(self, validated_data):
        logo = validated_data.pop("logo_p_upload", None)
        photos = validated_data.pop("photo_uploads", [])
        validated_data.pop("photo_remove_ids", None)
        return self._save_images(super().create(validated_data), logo, photos)

    @transaction.atomic
    def update(self, instance, validated_data):
        logo = validated_data.pop("logo_p_upload", None)
        photos = validated_data.pop("photo_uploads", [])
        removed = validated_data.pop("photo_remove_ids", [])
        product = super().update(instance, validated_data)
        self._remove_images(product, removed)
        return self._save_images(product, logo, photos)


class VariationImageMixin(serializers.Serializer):
    logo_p = serializers.SerializerMethodField()
    logo_image = serializers.PrimaryKeyRelatedField(
        queryset=Image.all_objects.all(), required=False, allow_null=True
    )

    def get_logo_p(self, obj):
        image = obj.logo_image
        if image:
            return image.public_url(self.context.get("request"))
        return ""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        product = attrs.get("product") or getattr(self.instance, "product", None)
        image = attrs.get("logo_image", getattr(self.instance, "logo_image", None))
        if image and product:
            linked = ProductImage.all_objects.filter(
                product=product, image=image, deleted_at__isnull=True
            ).exists()
            if not linked:
                raise serializers.ValidationError(
                    {"logo_image": "Escolha uma imagem da lista de fotos do produto."}
                )
        return attrs
