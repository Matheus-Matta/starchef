from rest_framework import serializers

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

        driver_type = attrs.get("driver_type", getattr(instance, "driver_type", Printer.DRIVER_BROWSER))
        drawer_enabled = attrs.get(
            "cash_drawer_enabled",
            getattr(instance, "cash_drawer_enabled", False),
        )
        drawer_pin = attrs.get("cash_drawer_pin", getattr(instance, "cash_drawer_pin", Printer.DRAWER_PIN_2))
        drawer_on = attrs.get("cash_drawer_on_ms", getattr(instance, "cash_drawer_on_ms", 100))
        drawer_off = attrs.get("cash_drawer_off_ms", getattr(instance, "cash_drawer_off_ms", 400))
        if drawer_enabled:
            # O pulso e um comando ESC/POS. No driver grafico do Windows os
            # mesmos bytes nao sao comando nenhum: sairiam impressos no papel.
            if driver_type != Printer.DRIVER_ESCPOS:
                errors["cash_drawer_enabled"] = (
                    "A gaveta so abre em impressoras com driver ESC/POS."
                )
            # Teto do proprio comando: `t1` e `t2` tem um byte cada, contado em
            # passos de 2 ms — 255 passos, 510 ms.
            for field, value, label in (
                ("cash_drawer_on_ms", drawer_on, "tempo ligado"),
                ("cash_drawer_off_ms", drawer_off, "intervalo desligado"),
            ):
                if not value or value > 510:
                    errors[field] = f"Informe um {label} entre 1 e 510 ms."
            if "cash_drawer_on_ms" not in errors and "cash_drawer_off_ms" not in errors:
                if drawer_off < drawer_on:
                    errors["cash_drawer_off_ms"] = (
                        "O intervalo desligado precisa ser maior ou igual ao tempo ligado."
                    )
        # `settings` e um JSONField: o cliente pode mandar lista, numero ou
        # texto. `dict(["a"])` levanta ValueError, que virava 500 — e o campo
        # aceita qualquer JSON, entao nao ha validacao de tipo antes daqui.
        raw_settings = attrs.get("settings", getattr(instance, "settings", {}) or {})
        if raw_settings in (None, ""):
            raw_settings = {}
        if not isinstance(raw_settings, dict):
            errors["settings"] = "As configurações da impressora precisam ser um objeto."
        if errors:
            raise serializers.ValidationError(errors)
        settings = dict(raw_settings)
        settings.update(
            {
                "connection_type": connection_type,
                "host": str(host) if host else None,
                "port": port,
                "timeout_seconds": timeout,
                # Espelhado como os campos de conexao: o PDV guarda uma copia
                # do cadastro junto do cupom na fila local, e le os dois niveis.
                "cash_drawer_enabled": bool(drawer_enabled),
                "cash_drawer_pin": drawer_pin,
                "cash_drawer_on_ms": drawer_on,
                "cash_drawer_off_ms": drawer_off,
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

    # A exclusividade da balança não é mais decidida aqui: o PDV lê a porta
    # serial direto (SerialScaleReader) e o sistema operacional, mais uma
    # trava de arquivo local, já garante que só uma janela usa o
    # equipamento por vez. O lease remoto por `agent_instance_id` era da
    # arquitetura anterior (LocalDeviceAgent consultando a API por peso) e
    # nenhum cliente envia mais esse campo — exigi-lo aqui só rejeitava
    # toda leitura automática de uma balança com `auto_print`.
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
