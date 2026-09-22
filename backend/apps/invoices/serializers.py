import re
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.x509.oid import NameOID
from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer
from apps.invoices.fiscal import format_access_key
from apps.invoices.models import (
    FiscalConfig,
    FiscalProfile,
    Invoice,
    InvoiceItem,
    validar_emissao_local,
)


def parse_and_validate_certificate(pfx_data: bytes, password: str | bytes):
    """Valida se o certificado e a senha abrem o PKCS#12 e extrai metadados."""
    pwd_bytes = password.encode() if isinstance(password, str) else (password or b"")
    try:
        private_key, cert, _ = load_key_and_certificates(pfx_data, pwd_bytes)
    except Exception as exc:
        err_msg = str(exc).lower()
        # `from exc` mantém o erro de criptografia na cadeia: é ele que
        # distingue "senha errada" de "arquivo corrompido" quando as duas
        # mensagens acima parecem igualmente plausíveis no suporte.
        if "mac" in err_msg or "decrypt" in err_msg or "password" in err_msg or "verify failure" in err_msg:
            raise serializers.ValidationError(
                {"certificate_password": "Senha incorreta para o certificado A1."}
            ) from exc
        raise serializers.ValidationError(
            {"certificate_file": "Arquivo de certificado A1 inválido ou corrompido (deve ser .pfx ou .p12)."}
        ) from exc

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
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)
    focus_connected = serializers.SerializerMethodField()
    focus_missing_fields = serializers.SerializerMethodField()
    provider_token_configured = serializers.SerializerMethodField()
    csc_token_configured = serializers.SerializerMethodField()
    focus_account_configured = serializers.SerializerMethodField()
    focus_company_dry_run = serializers.SerializerMethodField()
    has_certificate = serializers.SerializerMethodField()
    account_allows_local_fiscal = serializers.SerializerMethodField()
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
            "focus_company_id",
            "focus_sync_status",
            "focus_sync_error",
            "focus_synced_at",
            "focus_remote_data",
            "certificate_valid_until",
            "certificate_cnpj",
            "certificate_name",
        ]
        # CSC e a credencial do integrador: aceitam escrita, nunca voltam no GET.
        extra_kwargs = {
            "csc_token": {"write_only": True},
            "provider_token": {"write_only": True},
            "focus_token_production": {"write_only": True},
            "focus_token_homologation": {"write_only": True},
            "certificate_password": {"write_only": True},
        }

    def get_focus_connected(self, obj):
        return bool(obj.focus_company_id and (obj.focus_token_production or obj.focus_token_homologation))

    def get_account_allows_local_fiscal(self, obj):
        """A trava DE CIMA da emissão local, para a tela poder explicá-la.

        A autorização mora na conta, não na configuração fiscal — então ela não
        vem em `fields = "__all__"`. Sem este campo a tela só poderia mostrar o
        interruptor da loja, e ligar sem efeito é pior do que não poder ligar:
        o operador acha que ativou.
        """
        conta = getattr(obj, "account", None)
        return bool(getattr(conta, "local_fiscal_allowed", False))

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

    def _focus_account_config(self, obj):
        return getattr(obj.account, "focus_nfe_config", None)

    def get_focus_account_configured(self, obj):
        account_config = self._focus_account_config(obj)
        return bool(account_config and account_config.master_token and account_config.production_url)

    def get_focus_company_dry_run(self, obj):
        account_config = self._focus_account_config(obj)
        return bool(account_config and account_config.company_dry_run)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        managed_tokens = {"focus_token_production", "focus_token_homologation"}.intersection(attrs)
        if managed_tokens:
            raise serializers.ValidationError(
                {field: "Este token e administrado automaticamente pela sincronizacao Focus NFe." for field in managed_tokens}
            )
        provider = attrs.get("provider", getattr(self.instance, "provider", FiscalConfig.PROVIDER_MANUAL))

        # Emissão fiscal local: as MESMAS recusas do `clean()` do model, vindas
        # da mesma função. Duas cópias da regra viram duas regras.
        conta = attrs.get("account") or getattr(self.instance, "account", None)
        erros_locais = validar_emissao_local(
            local_fiscal_enabled=attrs.get(
                "local_fiscal_enabled",
                getattr(self.instance, "local_fiscal_enabled", False),
            ),
            local_fiscal_contingency=attrs.get(
                "local_fiscal_contingency",
                getattr(self.instance, "local_fiscal_contingency", False),
            ),
            provider=provider,
            conta_autoriza=bool(getattr(conta, "local_fiscal_allowed", False)),
        )
        if erros_locais:
            raise serializers.ValidationError(erros_locais)

        document_model = attrs.get("document_model", getattr(self.instance, "document_model", FiscalConfig.MODEL_NFCE))
        if provider == FiscalConfig.PROVIDER_FOCUS_NFE and document_model == FiscalConfig.MODEL_SAT:
            raise serializers.ValidationError({"document_model": "A Focus NFe desta integracao aceita NF-e ou NFC-e."})
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
        return self._validate_sefaz_certificate(attrs)

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

    def _validate_sefaz_certificate(self, attrs):
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
    order_sequence = serializers.IntegerField(source="order.sequence", read_only=True)

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
        # Nota fiscal negativa nao existe: devolucao tem natureza propria.
        # Aceitar o sinal invertido gravava um valor que a SEFAZ recusaria.

    def get_access_key_formatted(self, obj):
        return format_access_key(obj.access_key)
