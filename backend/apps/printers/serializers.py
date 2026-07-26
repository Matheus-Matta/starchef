from rest_framework import serializers
from django.utils import timezone

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.printers.models import Printer, PrintJob, Scale, ScaleReading


class PrinterSerializer(TenantModelSerializer):
    sector_name = serializers.CharField(source="sector.name", read_only=True, default=None)

    class Meta:
        model = Printer
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def validate(self, attrs):
        instance = self.instance
        connection_type = attrs.get(
            "connection_type",
            getattr(instance, "connection_type", Printer.CONNECTION_WINDOWS),
        )
        endpoint = attrs.get("endpoint", getattr(instance, "endpoint", ""))
        host = attrs.get("host", getattr(instance, "host", None))
        port = attrs.get("port", getattr(instance, "port", 9100))
        timeout = attrs.get(
            "timeout_seconds",
            getattr(instance, "timeout_seconds", 10),
        )
        errors = {}
        if connection_type in {
            Printer.CONNECTION_WINDOWS,
            Printer.CONNECTION_SERIAL,
        } and not str(endpoint or "").strip():
            errors["endpoint"] = (
                "Selecione a impressora do Windows."
                if connection_type == Printer.CONNECTION_WINDOWS
                else "Informe a porta serial, por exemplo COM3."
            )
        if connection_type == Printer.CONNECTION_NETWORK:
            if not host:
                errors["host"] = "Informe o endereço IP da impressora."
            if not port or port > 65535:
                errors["port"] = "Informe uma porta entre 1 e 65535."
        if not timeout or timeout > 120:
            errors["timeout_seconds"] = "Informe um timeout entre 1 e 120 segundos."
        if errors:
            raise serializers.ValidationError(errors)
        settings = dict(attrs.get("settings", getattr(instance, "settings", {}) or {}))
        settings.update(
            {
                "connection_type": connection_type,
                "host": str(host) if host else None,
                "port": port,
                "timeout_seconds": timeout,
            }
        )
        attrs["settings"] = settings
        return attrs


class ScaleSerializer(TenantModelSerializer):
    sector_name = serializers.CharField(source="sector.name", read_only=True, default=None)

    class Meta:
        model = Scale
        fields = "__all__"
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS,
            "agent_instance_id",
            "agent_lease_expires_at",
        ]


class ScaleReadingSerializer(TenantModelSerializer):
    net_weight_kg = serializers.DecimalField(max_digits=9, decimal_places=3, read_only=True)
    agent_instance_id = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )

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
        instance_id = attrs.pop("agent_instance_id", "")
        scale = attrs.get("scale")
        if scale and scale.auto_print:
            valid_lease = (
                instance_id
                and scale.agent_instance_id == instance_id
                and scale.agent_lease_expires_at
                and scale.agent_lease_expires_at > timezone.now()
            )
            if not valid_lease:
                raise serializers.ValidationError(
                    {
                        "agent_instance_id": (
                            "Esta balança não está reservada para este PDV. "
                            "A leitura automática foi ignorada."
                        )
                    }
                )
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
