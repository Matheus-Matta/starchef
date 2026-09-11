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


class ReusableAssetSerializer(TenantModelSerializer):
    current_stock = serializers.SerializerMethodField()
    current_stock_display = serializers.SerializerMethodField()
    total_entries = serializers.SerializerMethodField()
    total_losses = serializers.SerializerMethodField()
    is_below_minimum = serializers.SerializerMethodField()
    locations = serializers.SerializerMethodField()
    location_name = serializers.SerializerMethodField()
    stock_unit = serializers.CharField(default="UN", required=False)
    minimum_stock = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, allow_null=True)
    estimated_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    stock_status = serializers.SerializerMethodField()

    class Meta:
        from apps.menu.models import Product
        model = Product
        fields = [
            "id",
            "internal_code",
            "name",
            "brand",
            "model",
            "stock_unit",
            "current_stock",
            "current_stock_display",
            "minimum_stock",
            "is_below_minimum",
            "stock_status",
            "total_entries",
            "total_losses",
            "locations",
            "location_name",
            "estimated_cost",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS,
            "current_stock",
            "current_stock_display",
            "total_entries",
            "total_losses",
            "is_below_minimum",
            "stock_status",
            "locations",
            "location_name",
        ]

    def get_current_stock(self, obj):
        from apps.stock.models import StockMovement
        from django.db.models import Sum
        val = StockMovement.all_objects.filter(product=obj, deleted_at__isnull=True).aggregate(total=Sum("quantity"))["total"]
        return float(val) if val is not None else 0.0

    def get_current_stock_display(self, obj):
        qty = self.get_current_stock(obj)
        unit = (obj.stock_unit or "UN").upper()
        if qty == int(qty):
            return f"{int(qty)} {unit}"
        return f"{qty:.2f} {unit}"

    def get_total_entries(self, obj):
        from apps.stock.models import StockMovement
        from django.db.models import Sum
        val = StockMovement.all_objects.filter(product=obj, quantity__gt=0, deleted_at__isnull=True).aggregate(total=Sum("quantity"))["total"]
        return float(val) if val is not None else 0.0

    def get_total_losses(self, obj):
        from apps.stock.models import StockMovement
        from django.db.models import Sum
        val = StockMovement.all_objects.filter(product=obj, quantity__lt=0, deleted_at__isnull=True).aggregate(total=Sum("quantity"))["total"]
        return abs(float(val)) if val is not None else 0.0

    def get_is_below_minimum(self, obj):
        from decimal import Decimal
        if obj.minimum_stock is not None and obj.minimum_stock > 0:
            return Decimal(str(self.get_current_stock(obj))) < obj.minimum_stock
        return False

    def get_stock_status(self, obj):
        if obj.minimum_stock is not None and obj.minimum_stock > 0:
            return "ABAIXO DO MÍNIMO" if self.get_is_below_minimum(obj) else "NORMAL"
        return "SEM LIMITE"

    def get_locations(self, obj):
        from apps.stock.models import StockMovement
        return list(
            StockMovement.all_objects
            .filter(product=obj, location__isnull=False, deleted_at__isnull=True)
            .values_list("location__name", flat=True)
            .distinct()
        )

    def get_location_name(self, obj):
        from apps.stock.models import StockMovement
        last = (
            StockMovement.all_objects
            .filter(product=obj, location__isnull=False, deleted_at__isnull=True)
            .order_by("-created_at")
            .select_related("location")
            .first()
        )
        return last.location.name if last and last.location else "Sem local"


class ReusableAssetMovementSerializer(TenantModelSerializer):
    operator_name = serializers.CharField(source="operator.get_full_name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    nfe_number = serializers.CharField(source="nfe.number", read_only=True)
    movement_type_display = serializers.CharField(source="get_movement_type_display", read_only=True)

    class Meta:
        from apps.stock.models import StockMovement
        model = StockMovement
        fields = [
            "id",
            "movement_type",
            "movement_type_display",
            "quantity",
            "stock_unit",
            "unit_cost",
            "total_cost",
            "location_name",
            "operator_name",
            "nfe_number",
            "reason",
            "created_at",
        ]

