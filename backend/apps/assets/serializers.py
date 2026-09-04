from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer
from apps.assets.models import Asset, AssetDisposal, AssetLocationHistory


class AssetLocationHistorySerializer(TenantModelSerializer):
    from_location_name = serializers.CharField(source="from_location.name", read_only=True)
    to_location_name = serializers.CharField(source="to_location.name", read_only=True)
    moved_by_name = serializers.CharField(source="moved_by.get_full_name", read_only=True)

    class Meta:
        model = AssetLocationHistory
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class AssetDisposalSerializer(TenantModelSerializer):
    authorized_by_name = serializers.CharField(source="authorized_by.get_full_name", read_only=True)

    class Meta:
        model = AssetDisposal
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class AssetSerializer(TenantModelSerializer):
    name = serializers.CharField(source="product.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_internal_code = serializers.CharField(source="product.internal_code", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    responsible_person_name = serializers.CharField(source="responsible_person.get_full_name", read_only=True)
    invoice_number = serializers.CharField(source="nfe.number", read_only=True)
    is_under_warranty = serializers.SerializerMethodField()
    location_history = AssetLocationHistorySerializer(many=True, read_only=True)
    disposal = AssetDisposalSerializer(read_only=True)

    class Meta:
        model = Asset
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "asset_code", "qr_code_token"]

    def get_is_under_warranty(self, obj):
        from django.utils import timezone
        if obj.warranty_end_date:
            return obj.warranty_end_date >= timezone.now().date()
        return False
