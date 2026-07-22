from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.printers.models import Printer, PrintJob, Scale, ScaleReading


class PrinterSerializer(TenantModelSerializer):
    sector_name = serializers.CharField(source="sector.name", read_only=True, default=None)

    class Meta:
        model = Printer
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class ScaleSerializer(TenantModelSerializer):
    sector_name = serializers.CharField(source="sector.name", read_only=True, default=None)

    class Meta:
        model = Scale
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class ScaleReadingSerializer(TenantModelSerializer):
    net_weight_kg = serializers.DecimalField(max_digits=9, decimal_places=3, read_only=True)

    class Meta:
        model = ScaleReading
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "order_item"]
        extra_kwargs = {
            "restaurant": {"required": False},
            "branch": {"required": False},
        }

    def validate_weight_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError("Peso deve ser maior que zero.")
        return value

    def validate(self, attrs):
        tare = attrs.get("tare_kg") or 0
        weight = attrs.get("weight_kg")
        if weight is not None and tare and tare >= weight:
            raise serializers.ValidationError({"tare_kg": "Tara nao pode ser maior ou igual ao peso bruto."})
        return attrs


class PrintJobSerializer(TenantModelSerializer):
    class Meta:
        model = PrintJob
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS
