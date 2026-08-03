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

    class Meta:
        model = FiscalConfig
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "next_number"]
        # CSC e a credencial do integrador: aceitam escrita, nunca voltam no GET.
        extra_kwargs = {
            "csc_token": {"write_only": True},
            "provider_token": {"write_only": True},
        }


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
