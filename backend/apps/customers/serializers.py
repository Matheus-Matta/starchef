from apps.core.serializers import TenantModelSerializer

from apps.customers.models import Customer, CustomerAddress


class CustomerAddressSerializer(TenantModelSerializer):
    class Meta:
        model = CustomerAddress
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class CustomerSerializer(TenantModelSerializer):
    addresses = CustomerAddressSerializer(many=True, read_only=True)

    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]
