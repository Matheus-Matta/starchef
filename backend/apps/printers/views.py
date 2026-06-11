from rest_framework import viewsets

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin
from apps.printers.models import Printer, PrintJob
from apps.printers.serializers import PrinterSerializer, PrintJobSerializer


class PrinterViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = PrinterSerializer
    queryset = Printer.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "driver_type", "sector", "is_active"]
    search_fields = ["name", "endpoint"]


class PrintJobViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = PrintJobSerializer
    queryset = PrintJob.objects.select_related("restaurant", "branch", "printer", "order", "printed_by").all()
    filterset_fields = ["restaurant", "branch", "printer", "job_type", "status"]
    ordering_fields = ["created_at", "printed_at"]

