from apps.core.serializers import TenantModelSerializer

from apps.invoices.models import Invoice


class InvoiceSerializer(TenantModelSerializer):
    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]
