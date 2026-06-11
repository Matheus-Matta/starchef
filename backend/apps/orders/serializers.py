from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from apps.orders.models import Order, OrderItem, OrderItemAddon


class OrderItemAddonSerializer(TenantModelSerializer):
    addon_name = serializers.CharField(source="addon.name", read_only=True)

    class Meta:
        model = OrderItemAddon
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by", "total_price"]


class OrderItemSerializer(TenantModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
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
            "change_history",
        ]

