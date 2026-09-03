import re
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.x509.oid import NameOID
from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer
from apps.invoices.fiscal import format_access_key
from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice, InvoiceItem


def parse_and_validate_certificate(pfx_data: bytes, password: str | bytes):
    """Valida se o certificado e a senha abrem o PKCS#12 e extrai metadados."""
    pwd_bytes = password.encode() if isinstance(password, str) else (password or b"")
    try:
        private_key, cert, _ = load_key_and_certificates(pfx_data, pwd_bytes)
    except Exception as exc:
        err_msg = str(exc).lower()
        if "mac" in err_msg or "decrypt" in err_msg or "password" in err_msg or "verify failure" in err_msg:
            raise serializers.ValidationError({"certificate_password": "Senha incorreta para o certificado A1."})
        raise serializers.ValidationError({"certificate_file": "Arquivo de certificado A1 inválido ou corrompido (deve ser .pfx ou .p12)."})

    if not cert:
        raise serializers.ValidationError({"certificate_file": "Nenhum certificado encontrado no arquivo .pfx."})

    try:
        valid_until = cert.not_valid_after_utc
    except AttributeError:
        valid_until = cert.not_valid_after

    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = cn_attrs[0].value if cn_attrs else ""

    cnpj = ""
    cnpj_match = re.search(r"[:\s](\d{14})\b", cn) or re.search(r"\b(\d{14})\b", cn)
    if cnpj_match:
        cnpj = cnpj_match.group(1)

    return valid_until, cn, cnpj


class FiscalProfileSerializer(TenantModelSerializer):
    class Meta:
        model = FiscalProfile
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class FiscalConfigSerializer(TenantModelSerializer):
    is_ready = serializers.BooleanField(read_only=True)
    has_certificate = serializers.SerializerMethodField()
    has_certificate_password = serializers.SerializerMethodField()
    certificate_password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
        help_text="Senha do certificado A1.",
    )
    certificate_file = serializers.FileField(
        required=False,
        allow_null=True,
        help_text="Arquivo .pfx ou .p12 do certificado A1.",
    )
    dfe_ult_nsu = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Último NSU consultado na SEFAZ (DF-e).",
    )

    class Meta:
        model = FiscalConfig
        fields = "__all__"
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS,
            "next_number",
            "certificate_valid_until",
            "certificate_cnpj",
            "certificate_name",
        ]
        # CSC, senha do certificado e a credencial do integrador: aceitam escrita, nunca voltam no GET.
        extra_kwargs = {
            "csc_token": {"write_only": True},
            "provider_token": {"write_only": True},
            "certificate_password": {"write_only": True},
        }

    def get_has_certificate(self, obj):
        return bool(obj.certificate_file or obj.certificate_ref)

    def get_has_certificate_password(self, obj):
        return bool(obj.certificate_password)

    def to_internal_value(self, data):
        # Se certificate_file ou certificate_ref vierem como string (ex: URL ou path existente vindo de JSON),
        # removemos para não quebrar a validação de FileField do DRF.
        if isinstance(data, dict):
            data = data.copy()
            if "certificate_file" in data and not hasattr(data["certificate_file"], "read"):
                del data["certificate_file"]
            if "certificate_ref" in data and not hasattr(data["certificate_ref"], "read"):
                del data["certificate_ref"]
        return super().to_internal_value(data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            from apps.inbound_nfe.models import DFeSyncState
            state = None
            if instance.restaurant_id:
                state = DFeSyncState.all_objects.filter(
                    account=instance.account,
                    restaurant_id=instance.restaurant_id
                ).first()
            if not state and instance.branch_id:
                state = DFeSyncState.all_objects.filter(
                    account=instance.account,
                    branch_id=instance.branch_id
                ).first()
            if state:
                data["dfe_ult_nsu"] = state.ult_nsu
                data["dfe_last_sync_at"] = state.last_sync_at
                data["dfe_next_allowed_at"] = state.next_allowed_at
                data["dfe_last_cstat"] = state.last_cstat
            else:
                data["dfe_ult_nsu"] = "000000000000000"
        except Exception:
            data["dfe_ult_nsu"] = "000000000000000"
        return data

    def validate(self, attrs):
        attrs = super().validate(attrs)
        file_obj = attrs.get("certificate_file")
        password = attrs.get("certificate_password")

        if file_obj:
            pfx_data = file_obj.read()
            file_obj.seek(0)
            pwd = password or (self.instance.certificate_password if self.instance else "")
            valid_until, cn, cnpj = parse_and_validate_certificate(pfx_data, pwd)
            attrs["certificate_valid_until"] = valid_until
            attrs["certificate_name"] = cn
            if cnpj:
                attrs["certificate_cnpj"] = cnpj
            if not attrs.get("certificate_ref"):
                attrs["certificate_ref"] = getattr(file_obj, "name", "certificate.pfx")
        elif password and self.instance and self.instance.certificate_file:
            try:
                with self.instance.certificate_file.open("rb") as f:
                    pfx_data = f.read()
                valid_until, cn, cnpj = parse_and_validate_certificate(pfx_data, password)
                attrs["certificate_valid_until"] = valid_until
                attrs["certificate_name"] = cn
                if cnpj:
                    attrs["certificate_cnpj"] = cnpj
            except Exception as exc:
                if isinstance(exc, serializers.ValidationError):
                    raise
        return attrs

    def create(self, validated_data):
        dfe_nsu = validated_data.pop("dfe_ult_nsu", None)
        instance = super().create(validated_data)
        self._ensure_dfe_sync_state(instance, dfe_nsu=dfe_nsu)
        return instance

    def update(self, instance, validated_data):
        dfe_nsu = validated_data.pop("dfe_ult_nsu", None)
        instance = super().update(instance, validated_data)
        self._ensure_dfe_sync_state(instance, dfe_nsu=dfe_nsu)
        return instance

    def _ensure_dfe_sync_state(self, instance, dfe_nsu=None):
        try:
            import re
            from apps.inbound_nfe.models import DFeSyncState

            cnpj = re.sub(r'\D', '', instance.cnpj or instance.certificate_cnpj or '')
            environment = (
                "homologation"
                if instance.environment == FiscalConfig.ENV_HOMOLOGATION
                else "production"
            )

            state = None
            if instance.restaurant_id:
                state = DFeSyncState.all_objects.filter(
                    account=instance.account,
                    restaurant_id=instance.restaurant_id
                ).first()

            if not state and instance.branch_id:
                state = DFeSyncState.all_objects.filter(
                    account=instance.account,
                    branch_id=instance.branch_id
                ).first()

            if not state:
                state, _ = DFeSyncState.all_objects.get_or_create(
                    account=instance.account,
                    branch=instance.branch,
                    restaurant=instance.restaurant,
                    defaults={
                        'cnpj': cnpj,
                        'environment': environment,
                        'ult_nsu': str(dfe_nsu).strip().zfill(15) if dfe_nsu else "000000000000000",
                    }
                )

            updated = False
            if cnpj and state.cnpj != cnpj:
                state.cnpj = cnpj
                updated = True
            if state.environment != environment:
                state.environment = environment
                updated = True
            if dfe_nsu is not None and str(dfe_nsu).strip():
                clean_nsu = str(dfe_nsu).strip().zfill(15)
                if state.ult_nsu != clean_nsu:
                    state.ult_nsu = clean_nsu
                    # Ao alterar o NSU manualmente, limpa eventual bloqueio para permitir consulta imediata
                    state.next_allowed_at = None
                    state.sync_error_count = 0
                    updated = True

            if updated:
                state.save()
        except Exception:
            pass


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
