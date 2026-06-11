from apps.core.serializers import TenantModelSerializer

from apps.printers.models import Printer, PrintJob


class PrinterSerializer(TenantModelSerializer):
    class Meta:
        model = Printer
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class PrintJobSerializer(TenantModelSerializer):
    class Meta:
        model = PrintJob
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]
