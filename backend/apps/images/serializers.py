"""Campos e mixins de serializer para os vinculos de imagem."""
from django.db import transaction
from rest_framework import serializers

from apps.images.models import Image
from apps.images.validation import validate_image_upload


class ValidatedImageField(serializers.ImageField):
    def to_internal_value(self, data):
        uploaded = super().to_internal_value(data)
        uploaded._starchef_image_metadata = validate_image_upload(uploaded)
        return uploaded


class ImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Image
        fields = [
            "id", "url", "original_name", "content_type", "size", "width",
            "height", "checksum", "alt_text", "created_at",
        ]
        read_only_fields = fields

    def get_url(self, obj):
        return obj.public_url(self.context.get("request"))


class LogoImageMixin(serializers.Serializer):
    logo_url = serializers.SerializerMethodField()
    logo_image = serializers.UUIDField(source="logo_image_id", read_only=True)
    logo_upload = ValidatedImageField(write_only=True, required=False)

    def get_logo_url(self, obj):
        image = getattr(obj, "logo_image", None)
        if image:
            return image.public_url(self.context.get("request"))
        legacy = getattr(obj, "logo", None)
        if not legacy:
            return ""
        try:
            url = legacy.url
        except ValueError:
            return ""
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request and not url.startswith("http") else url

    def _save_logo(self, instance, uploaded):
        if uploaded is None:
            return instance
        request = self.context.get("request")
        instance.logo_image = Image.create_from_upload(
            uploaded, account=instance.account, user=getattr(request, "user", None)
        )
        instance.save(update_fields=["logo_image", "updated_at"])
        return instance

    @transaction.atomic
    def create(self, validated_data):
        uploaded = validated_data.pop("logo_upload", None)
        return self._save_logo(super().create(validated_data), uploaded)

    @transaction.atomic
    def update(self, instance, validated_data):
        uploaded = validated_data.pop("logo_upload", None)
        return self._save_logo(super().update(instance, validated_data), uploaded)


def image_data(image, serializer, *, primary=False, position=0):
    data = ImageSerializer(image, context=serializer.context).data
    return {**data, "is_primary": primary, "position": position}
