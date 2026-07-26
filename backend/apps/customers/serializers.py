from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.customers.models import Customer, CustomerAddress
from apps.customers.validators import format_cpf, is_valid_cpf, mask_cpf, mask_phone, strip_cpf

# Perfis autorizados a ver dados pessoais completos (CPF/telefone) nas listagens.
SENSITIVE_DATA_PROFILES = {"admin", "owner", "manager", "cashier"}


class CustomerAddressSerializer(TenantModelSerializer):
    class Meta:
        model = CustomerAddress
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class CustomerSerializer(TenantModelSerializer):
    addresses = CustomerAddressSerializer(many=True, read_only=True)
    address = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def validate_document(self, value):
        # CPF é opcional; quando informado, precisa ser válido (STC-043).
        if not value:
            return value
        if not is_valid_cpf(value):
            raise serializers.ValidationError("CPF inválido.")
        return format_cpf(value)

    def validate(self, attrs):
        address = attrs.get("address")
        address_fields = {"street", "number", "complement", "district", "city", "state", "zip_code", "reference"}
        has_address = bool(address and any(str(address.get(key, "")).strip() for key in address_fields))
        if has_address:
            required = {"street": "Rua", "city": "Cidade", "state": "UF"}
            errors = {
                key: f"{label} é obrigatório."
                for key, label in required.items()
                if not str(address.get(key, "")).strip()
            }
            state = str(address.get("state", "")).strip()
            if state and len(state) != 2:
                errors["state"] = "Informe a UF com 2 letras."
            if errors:
                raise serializers.ValidationError({"address": errors})
        elif address is not None:
            attrs.pop("address")
        attrs = super().validate(attrs)
        # CPF único por conta quando informado (evita duplicidade silenciosa).
        document = attrs.get("document")
        if document:
            digits = strip_cpf(document)
            candidates = Customer.objects.filter(document__contains=digits[:3]) if digits else Customer.objects.none()
            for other in candidates:
                if strip_cpf(other.document) == digits and (self.instance is None or other.pk != self.instance.pk):
                    raise serializers.ValidationError({"document": "Já existe um cliente com este CPF."})
        return attrs

    def _save_primary_address(self, customer, address):
        if not address:
            return
        address = dict(address)
        address["state"] = str(address.get("state", "")).strip().upper()
        address.setdefault("label", "Principal")
        address["is_default"] = True
        defaults = {
            **address,
            "account": customer.account,
            "restaurant": customer.restaurant,
            "branch": customer.branch,
        }
        current = customer.addresses.filter(is_default=True).first() or customer.addresses.first()
        if current:
            for key, value in defaults.items():
                setattr(current, key, value)
            current.save()
        else:
            CustomerAddress.objects.create(customer=customer, **defaults)

    def create(self, validated_data):
        address = validated_data.pop("address", None)
        customer = super().create(validated_data)
        self._save_primary_address(customer, address)
        return customer

    def update(self, instance, validated_data):
        address = validated_data.pop("address", None)
        customer = super().update(instance, validated_data)
        self._save_primary_address(customer, address)
        return customer

    def _can_view_sensitive(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        profile = getattr(user, "profile", None)
        return bool(profile and profile.profile_type in SENSITIVE_DATA_PROFILES)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        primary = instance.addresses.filter(is_default=True).first() or instance.addresses.first()
        data["address"] = CustomerAddressSerializer(primary, context=self.context).data if primary else None
        # Mascara CPF/telefone nas LISTAGENS quando o perfil não tem permissão
        # de dados sensíveis (STC-044). No detalhe/edição os dados são exibidos.
        view = self.context.get("view")
        is_list = getattr(view, "action", None) == "list"
        if is_list and not self._can_view_sensitive():
            if data.get("document"):
                data["document"] = mask_cpf(data["document"])
            if data.get("phone"):
                data["phone"] = mask_phone(data["phone"])
        return data
