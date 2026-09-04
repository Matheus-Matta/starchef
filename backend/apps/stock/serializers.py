from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer
from apps.stock.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    InventoryLot,
    StockLocation,
    StockMovement,
)


class StockLocationSerializer(TenantModelSerializer):
    class Meta:
        model = StockLocation
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class GoodsReceiptItemSerializer(TenantModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_code = serializers.CharField(source="product.internal_code", read_only=True)
    stock_unit = serializers.CharField(source="product.stock_unit", read_only=True)

    class Meta:
        model = GoodsReceiptItem
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class GoodsReceiptSerializer(TenantModelSerializer):
    items = GoodsReceiptItemSerializer(many=True, read_only=True)
    received_by_name = serializers.CharField(source="received_by.get_full_name", read_only=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    supplier_name = serializers.CharField(source="invoice.supplier_name", read_only=True)
    location_name = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceipt
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_location_name(self, obj):
        if obj.location:
            return obj.location.name
        from apps.assets.models import Asset
        asset = Asset.all_objects.filter(receipt=obj).select_related("location").first()
        if asset and asset.location:
            return asset.location.name
        if obj.invoice:
            from apps.stock.models import StockMovement
            sm = StockMovement.all_objects.filter(nfe=obj.invoice, location__isnull=False).select_related("location").first()
            if sm and sm.location:
                return sm.location.name
        return None


class InventoryLotSerializer(TenantModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    stock_unit = serializers.CharField(source="product.stock_unit", read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = InventoryLot
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_is_expired(self, obj):
        from django.utils import timezone
        if obj.expiration_date:
            return obj.expiration_date < timezone.now().date()
        return False


class StockMovementSerializer(TenantModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    operator_name = serializers.CharField(source="operator.get_full_name", read_only=True)
    lot_number = serializers.CharField(source="inventory_lot.lot_number", read_only=True)
    nfe_number = serializers.CharField(source="nfe.number", read_only=True)

    class Meta:
        model = StockMovement
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "total_cost"]

