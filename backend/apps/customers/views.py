from django.db.models import Count

from apps.core.viewsets import BaseTenantViewSet
from apps.customers.models import Customer, CustomerAddress, CustomerGroup
from apps.customers.serializers import (
    CustomerAddressSerializer,
    CustomerGroupSerializer,
    CustomerSerializer,
)


class CustomerGroupViewSet(BaseTenantViewSet):
    """Cadastro dos grupos de clientes."""

    serializer_class = CustomerGroupSerializer
    # A contagem sai na MESMA consulta da listagem: sem isto, desenhar uma
    # grade de cinquenta grupos custaria cinquenta idas ao banco só para
    # escrever o número ao lado do nome.
    queryset = CustomerGroup.objects.annotate(total_clientes=Count("customers", distinct=True)).all()
    filterset_fields = ["is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]


class CustomerViewSet(BaseTenantViewSet):
    serializer_class = CustomerSerializer
    # `groups` no prefetch: a grade mostra os grupos de cada cliente, e sem
    # isto seriam N consultas para escrever os selos de uma página.
    queryset = Customer.objects.prefetch_related("addresses", "groups").all()
    filterset_fields = ["is_active", "groups"]
    search_fields = ["name", "phone", "email", "document"]
    ordering_fields = ["name", "created_at"]


class CustomerAddressViewSet(BaseTenantViewSet):
    serializer_class = CustomerAddressSerializer
    queryset = CustomerAddress.objects.select_related("customer", "restaurant", "branch").all()
    filterset_fields = ["customer", "city", "district"]
    search_fields = ["street", "district", "city", "reference"]

