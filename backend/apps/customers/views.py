from rest_framework import viewsets

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin
from apps.customers.models import Customer, CustomerAddress
from apps.customers.serializers import CustomerAddressSerializer, CustomerSerializer


class CustomerViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    queryset = Customer.objects.prefetch_related("addresses").all()
    filterset_fields = ["restaurant", "branch", "is_active"]
    search_fields = ["name", "phone", "email", "document"]
    ordering_fields = ["name", "created_at"]


class CustomerAddressViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = CustomerAddressSerializer
    queryset = CustomerAddress.objects.select_related("customer", "restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "customer", "city", "district"]
    search_fields = ["street", "district", "city", "reference"]

