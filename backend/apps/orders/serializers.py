from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from apps.orders.models import Order, OrderBatch, OrderItem, OrderItemAddon


class OrderItemAddonSerializer(TenantModelSerializer):
    addon_name = serializers.CharField(source="addon.name", read_only=True)

    class Meta:
        model = OrderItemAddon
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by", "total_price"]


class OrderItemSerializer(TenantModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)
    # Fields for KDS display
    order_sequence = serializers.IntegerField(source="order.sequence", read_only=True)
    order_type = serializers.CharField(source="order.order_type", read_only=True)
    order_table_number = serializers.SerializerMethodField()
    order_command_code = serializers.SerializerMethodField()
    batch_number = serializers.IntegerField(source="batch.batch_number", read_only=True, default=None)
    addons = OrderItemAddonSerializer(many=True, read_only=True)

    class Meta:
        model = OrderItem
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "total_price",
            "sent_to_kitchen_at",
            "preparation_started_at",
            "ready_at",
            "delivered_at",
        ]

    def get_order_table_number(self, obj):
        try:
            return obj.order.table.number if obj.order.table_id else None
        except Exception:
            return None

    def get_order_command_code(self, obj):
        try:
            return obj.order.command.code if obj.order.command_id else None
        except Exception:
            return None


class OrderBatchSerializer(TenantModelSerializer):
    sent_by_name = serializers.CharField(source="sent_by.get_full_name", read_only=True, default=None)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = OrderBatch
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by", "batch_number", "sent_at"]


class OrderSerializer(TenantModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    table_number = serializers.CharField(source="table.number", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = [
            "id",
            "sequence",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "opened_at",
            "closed_at",
            "subtotal",
            "service_fee",
            "total",
            "payment_status",
            "production_status",
            "change_history",
        ]
