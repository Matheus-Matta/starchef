from rest_framework import serializers
from apps.core.serializers import TenantModelSerializer
from apps.inbound_nfe.models import (
    InboundNFe,
    InboundNFeItem,
    SupplierItemMapping,
    DFeDistributionDocument,
    DFeSyncState,
    NFeManifestation,
)


class NFeManifestationSerializer(TenantModelSerializer):
    class Meta:
        model = NFeManifestation
        fields = [
            "id", "event_type", "event_code", "sequence", "event_datetime",
            "status", "sefaz_batch_status", "sefaz_batch_reason",
            "sefaz_event_status", "sefaz_event_reason", "protocol",
            "registered_at", "reason"
        ]
        read_only_fields = fields


class DFeDistributionDocumentSerializer(TenantModelSerializer):
    class Meta:
        model = DFeDistributionDocument
        fields = [
            "id", "nsu", "schema", "access_key", "document_type",
            "received_at", "processed_at", "processing_status", "processing_error"
        ]
        read_only_fields = fields


class DFeSyncStateSerializer(TenantModelSerializer):
    class Meta:
        model = DFeSyncState
        fields = [
            "id", "cnpj", "environment", "ult_nsu", "max_nsu",
            "last_cstat", "last_reason", "last_sync_at", "next_allowed_at",
            "is_syncing", "sync_error_count"
        ]
        read_only_fields = fields


class InboundNFeItemSerializer(TenantModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True, default=None)
    product_name = serializers.CharField(source="product.name", read_only=True, default=None)
    product_item_type = serializers.CharField(source="product.item_type", read_only=True, default=None)
    product_tracking_mode = serializers.CharField(source="product.tracking_mode", read_only=True, default=None)
    product_requires_lot_control = serializers.BooleanField(source="product.requires_lot_control", read_only=True, default=False)
    product_requires_serial_number = serializers.BooleanField(source="product.requires_serial_number", read_only=True, default=False)
    product_brand = serializers.CharField(source="product.brand", read_only=True, default=None)
    product_model = serializers.CharField(source="product.model", read_only=True, default=None)
    is_asset = serializers.SerializerMethodField()

    class Meta:
        model = InboundNFeItem
        fields = [
            "id", "item_number", "supplier_code", "ean", "ean_trib",
            "description", "ncm", "cest", "cfop", "commercial_unit",
            "commercial_quantity", "commercial_unit_value", "product_total",
            "discount", "freight", "insurance", "other_expenses",
            "tax_data", "ingredient", "ingredient_name", "product", "product_name",
            "product_item_type", "product_tracking_mode", "product_requires_lot_control", "product_requires_serial_number",
            "product_brand", "product_model", "is_asset",
            "conversion_factor", "received_quantity", "stock_movement"
        ]

    def get_is_asset(self, obj):
        if not obj.product:
            return False
        return (
            obj.product.item_type in ("EQUIPMENT", "FIXED_ASSET")
            or obj.product.tracking_mode == "SERIALIZED"
            or obj.product.requires_serial_number
        )


class InboundNFeSerializer(TenantModelSerializer):
    items = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    unmapped_items_count = serializers.SerializerMethodField()
    has_unmapped_items = serializers.SerializerMethodField()
    latest_manifestation = serializers.SerializerMethodField()

    class Meta:
        model = InboundNFe
        fields = [
            "id", "access_key", "nsu", "number", "series", "issue_date",
            "supplier_cnpj", "supplier_name", "total_products",
            "total_invoice", "status", "distribution_type", "xml_status",
            "manifestation_status", "receiving_status",
            "stock_applied_at", "items", "items_count",
            "unmapped_items_count", "has_unmapped_items", "latest_manifestation"
        ]

    def get_latest_manifestation(self, obj):
        latest = NFeManifestation.all_objects.filter(invoice=obj).order_by("-created_at").first()
        if not latest:
            return None
        return NFeManifestationSerializer(latest).data

    def get_items(self, obj):
        # Na listagem comum de tabela, não precisa serializar a árvore completa de itens
        # a menos que seja detalhe (retrieve) ou chamado explicitamente
        view = self.context.get("view")
        if view and getattr(view, "action", None) == "list":
            return []
        items_qs = InboundNFeItem.all_objects.filter(invoice=obj).order_by("item_number")
        return InboundNFeItemSerializer(items_qs, many=True, context=self.context).data

    def get_items_count(self, obj):
        return InboundNFeItem.all_objects.filter(invoice=obj).count()

    def get_unmapped_items_count(self, obj):
        if obj.status in (InboundNFe.STATUS_SUMMARY, InboundNFe.STATUS_CANCELLED):
            return 0
        return InboundNFeItem.all_objects.filter(
            invoice=obj,
            ingredient__isnull=True,
            product__isnull=True
        ).count()

    def get_has_unmapped_items(self, obj):
        if obj.status in (InboundNFe.STATUS_SUMMARY, InboundNFe.STATUS_CANCELLED, InboundNFe.STATUS_RECEIVED):
            return False
        return InboundNFeItem.all_objects.filter(
            invoice=obj,
            ingredient__isnull=True,
            product__isnull=True
        ).exists()


class InboundNFeItemMapRequestSerializer(serializers.Serializer):
    product_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    ingredient_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    conversion_factor = serializers.DecimalField(max_digits=12, decimal_places=6, default=1)
    save_supplier_mapping = serializers.BooleanField(default=True)


class ReceiveInvoiceItemSerializer(serializers.Serializer):
    item_id = serializers.CharField(required=True)
    received_quantity = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    accepted_quantity = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    rejected_quantity = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, default=0)
    conversion_factor = serializers.DecimalField(max_digits=12, decimal_places=6, required=False, default=1)
    lot_number = serializers.CharField(required=False, allow_blank=True, default="")
    manufacturing_date = serializers.DateField(required=False, allow_null=True, default=None)
    expiration_date = serializers.DateField(required=False, allow_null=True, default=None)
    serials = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        default=list
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ReceiveInvoiceRequestSerializer(serializers.Serializer):
    location_id = serializers.CharField(required=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    items = ReceiveInvoiceItemSerializer(many=True, required=True)
