from rest_framework import viewsets

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin
from apps.invoices.models import Invoice
from apps.invoices.serializers import InvoiceSerializer


class InvoiceViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.select_related("restaurant", "branch", "order").all()
    filterset_fields = ["restaurant", "branch", "status", "phase"]
    search_fields = ["number", "provider"]

