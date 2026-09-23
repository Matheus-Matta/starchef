from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer
from apps.orders.models import CommandItem


class CommandItemSerializer(TenantModelSerializer):
    """Anotação de comanda no mesmo formato visual de um item de pedido."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    pricing_unit = serializers.CharField(source="product.pricing_unit", read_only=True)
    command_number = serializers.IntegerField(source="command.number", read_only=True)
    command_code = serializers.CharField(source="command.code", read_only=True)
    table_number = serializers.IntegerField(source="table.number", read_only=True, default=None)
    batch_number = serializers.IntegerField(source="batch.batch_number", read_only=True, default=None)
    origin = serializers.SerializerMethodField()
    addons = serializers.SerializerMethodField()

    class Meta:
        model = CommandItem
        fields = [
            "id",
            "command",
            "command_number",
            "command_code",
            "table",
            "table_number",
            "product",
            "product_name",
            "pricing_unit",
            "quantity",
            "unit_price",
            "total_price",
            "variations",
            "addons",
            "customer_note",
            "production_sector",
            "status",
            "command_status",
            "command_closed_at",
            "batch",
            "batch_number",
            "launched_at",
            "sent_to_kitchen_at",
            "preparation_started_at",
            "ready_at",
            "delivered_at",
            "void_reason",
            "voided_at",
            "origin",
        ]
        read_only_fields = ["command_status", "command_closed_at", "launched_at"]

    def get_origin(self, obj):
        return "command"

    def get_addons(self, obj):
        return [
            {
                "id": str(entry.id),
                "addon": str(entry.addon_id),
                "addon_name": entry.addon.name,
                "quantity": entry.quantity,
                "unit_price": entry.unit_price,
                "total_price": entry.total_price,
            }
            for entry in obj.addons.all()
        ]
