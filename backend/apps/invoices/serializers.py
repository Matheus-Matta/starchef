from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.invoices.fiscal import format_access_key
from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice, InvoiceItem


class FiscalProfileSerializer(TenantModelSerializer):
    class Meta:
        model = FiscalProfile
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class FiscalConfigSerializer(TenantModelSerializer):
    is_ready = serializers.BooleanField(read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)
    focus_connected = serializers.SerializerMethodField()
    focus_missing_fields = serializers.SerializerMethodField()
    provider_token_configured = serializers.SerializerMethodField()
    csc_token_configured = serializers.SerializerMethodField()
    focus_certificate_configured = serializers.SerializerMethodField()
    focus_certificate_password_configured = serializers.SerializerMethodField()
    focus_account_configured = serializers.SerializerMethodField()
    focus_company_dry_run = serializers.SerializerMethodField()

    class Meta:
        model = FiscalConfig
        fields = "__all__"
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS,
            "next_number",
            "focus_company_id",
            "focus_sync_status",
            "focus_sync_error",
            "focus_synced_at",
            "focus_remote_data",
        ]
        # CSC e a credencial do integrador: aceitam escrita, nunca voltam no GET.
        extra_kwargs = {
            "csc_token": {"write_only": True},
            "provider_token": {"write_only": True},
            "focus_token_production": {"write_only": True},
            "focus_token_homologation": {"write_only": True},
            "focus_certificate_base64": {"write_only": True},
            "focus_certificate_password": {"write_only": True},
        }

    def get_focus_connected(self, obj):
        return bool(obj.focus_company_id and (obj.focus_token_production or obj.focus_token_homologation))

    def get_focus_missing_fields(self, obj):
        """O que ainda falta para a Focus aceitar a empresa, campo a campo.

        A API de sincronizacao ja recusa com a lista ("...antes de sincronizar:
        CEP."), mas so DEPOIS de clicar. Devolvendo isso no GET a tela mostra a
        pendencia antes, apontando o campo exato em vez de mandar o usuario
        adivinhar onde mexer.
        """
        from apps.invoices.focus import company_payload_missing_fields

        return company_payload_missing_fields(obj)

    def get_provider_token_configured(self, obj):
        return bool(obj.provider_token)

    def get_csc_token_configured(self, obj):
        return bool(obj.csc_token)

    def get_focus_certificate_configured(self, obj):
        return bool(obj.focus_certificate_base64)

    def get_focus_certificate_password_configured(self, obj):
        return bool(obj.focus_certificate_password)

    def _focus_account_config(self, obj):
        return getattr(obj.account, "focus_nfe_config", None)

    def get_focus_account_configured(self, obj):
        account_config = self._focus_account_config(obj)
        return bool(account_config and account_config.master_token and account_config.production_url)

    def get_focus_company_dry_run(self, obj):
        account_config = self._focus_account_config(obj)
        return bool(account_config and account_config.company_dry_run)

    def validate(self, attrs):
        managed_tokens = {"focus_token_production", "focus_token_homologation"}.intersection(attrs)
        if managed_tokens:
            raise serializers.ValidationError(
                {field: "Este token e administrado automaticamente pela sincronizacao Focus NFe." for field in managed_tokens}
            )
        provider = attrs.get("provider", getattr(self.instance, "provider", FiscalConfig.PROVIDER_MANUAL))
        document_model = attrs.get("document_model", getattr(self.instance, "document_model", FiscalConfig.MODEL_NFCE))
        if provider == FiscalConfig.PROVIDER_FOCUS_NFE and document_model == FiscalConfig.MODEL_SAT:
            raise serializers.ValidationError({"document_model": "A Focus NFe desta integracao aceita NF-e ou NFC-e."})
        certificate = attrs.get("focus_certificate_base64")
        certificate_password = attrs.get("focus_certificate_password")
        if certificate and provider != FiscalConfig.PROVIDER_FOCUS_NFE:
            raise serializers.ValidationError(
                {"focus_certificate_base64": "O envio automatico do certificado exige o provedor Focus NFe."}
            )
        if bool(certificate) != bool(certificate_password):
            raise serializers.ValidationError(
                {"focus_certificate_base64": "Envie o certificado A1 e sua senha na mesma operacao."}
            )
        csc_id = attrs.get("csc_id")
        if csc_id and not csc_id.isdigit():
            raise serializers.ValidationError({"csc_id": "Informe apenas numeros no ID do CSC."})
        branch = attrs.get("branch", getattr(self.instance, "branch", None))
        if branch is not None:
            duplicates = FiscalConfig.all_objects.filter(branch=branch)
            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                # A constraint e do banco e nao enxerga soft-delete: sem isto o
                # POST estourava IntegrityError ("valor duplicado") em vez de
                # dizer que a configuracao daquela filial ja existe.
                raise serializers.ValidationError(
                    {"branch": "Esta filial ja possui uma configuracao fiscal. Edite a existente em vez de criar outra."}
                )
        return attrs


class InvoiceItemSerializer(TenantModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class InvoiceSerializer(TenantModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    access_key_formatted = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS,
            "access_key",
            "provider_reference",
            "emission_type",
            "authorization_protocol",
            "authorized_at",
            "digest_value",
            "qr_code_data",
            "status",
            "issued_at",
        ]

    def get_access_key_formatted(self, obj):
        return format_access_key(obj.access_key)
