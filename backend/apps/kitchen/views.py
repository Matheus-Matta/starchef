import django_filters
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet, ReadOnlyTenantViewSet
from apps.orders.models import Order, OrderItem
from apps.orders.serializers import OrderItemSerializer, OrderSerializer
from apps.orders.services import update_order_item_status
from apps.restaurants.models import Restaurant

from .models import KdsColumn, KdsStation
from .serializers import KdsColumnSerializer, KdsStationSerializer
from .station_templates import STATION_TEMPLATES, TEMPLATES_BY_KEY

# Orders active in the kitchen — exclude definitively closed/cancelled
_INACTIVE_ORDER_STATUSES = [Order.STATUS_CANCELLED, Order.STATUS_REFUNDED]
_ACTIVE_PRODUCTION_STATUSES = [
    Order.PROD_SENT,
    Order.PROD_PREPARING,
    Order.PROD_PARTIALLY_READY,
    Order.PROD_READY,
]

_ACTIVE_ITEM_STATUSES = [OrderItem.STATUS_SENT, OrderItem.STATUS_PREPARING, OrderItem.STATUS_READY]


class KitchenOrderViewSet(ReadOnlyTenantViewSet):
    serializer_class = OrderSerializer
    queryset = (
        Order.objects.select_related("restaurant", "branch", "table", "command", "customer")
        .prefetch_related("items__product", "items__addons", "items__batch")
        .exclude(status__in=_INACTIVE_ORDER_STATUSES)
        .filter(production_status__in=_ACTIVE_PRODUCTION_STATUSES)
    )
    filterset_fields = ["status", "production_status", "order_type", "items__production_sector"]
    ordering_fields = ["opened_at", "sequence"]

    def list(self, request, *args, **kwargs):
        from apps.orders.services import dispatch_due_kitchen_batches

        account = getattr(request, "account", None)
        if account is not None:
            dispatch_due_kitchen_batches(account_id=account.id)
        return super().list(request, *args, **kwargs)


class KitchenItemFilter(django_filters.FilterSet):
    """Filtro do KDS: setor/status + intervalo de datas (por data de lançamento)."""

    launched_after = django_filters.DateFilter(field_name="launched_at", lookup_expr="date__gte")
    launched_before = django_filters.DateFilter(field_name="launched_at", lookup_expr="date__lte")

    class Meta:
        model = OrderItem
        fields = ["production_sector", "status"]


class KitchenItemViewSet(ReadOnlyTenantViewSet):
    serializer_class = OrderItemSerializer
    queryset = (
        OrderItem.objects.select_related("restaurant", "branch", "order__table", "order__command", "product", "batch")
        .prefetch_related("addons")
        .all()
    )
    filterset_class = KitchenItemFilter
    ordering_fields = ["launched_at", "ready_at", "sent_to_kitchen_at"]

    def list(self, request, *args, **kwargs):
        from apps.orders.services import dispatch_due_kitchen_batches

        account = getattr(request, "account", None)
        if account is not None:
            dispatch_due_kitchen_batches(account_id=account.id)
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(status__in=_ACTIVE_ITEM_STATUSES)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        try:
            item = update_order_item_status(
                self.get_object(),
                request.data["status"],
                request.user,
                reason=request.data.get("reason", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"], url_path="move")
    def move(self, request, pk=None):
        """Move um card (item) para uma coluna do quadro (drag-and-drop).

        Grava a coluna atual e sincroniza o status para manter a vida do item
        coerente: entrar numa coluna `is_done` conclui (marca "pronto"); sair da
        coluna de entrada para uma coluna comum inicia o preparo. Movimentos que
        não sejam esses só reposicionam o card (colunas são livres).
        """
        item = self.get_object()
        account = getattr(request, "account", None)
        column_id = request.data.get("column")
        column = None
        if column_id:
            column = KdsColumn.objects.filter(pk=column_id, account=account).select_related("station").first()
            if column is None:
                return Response({"detail": "Coluna inválida para esta conta."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if column and column.is_done and item.status != OrderItem.STATUS_READY:
                item = update_order_item_status(item, OrderItem.STATUS_READY, request.user)
            elif column and not column.is_done and not column.is_entry and item.status == OrderItem.STATUS_SENT:
                item = update_order_item_status(item, OrderItem.STATUS_PREPARING, request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        item.kds_column = column
        item.save(update_fields=["kds_column", "updated_at"])
        return Response(self.get_serializer(item).data)


class KdsStationViewSet(BaseTenantViewSet):
    serializer_class = KdsStationSerializer
    queryset = KdsStation.objects.prefetch_related("columns").all()
    filterset_fields = ["is_active"]

    @action(detail=False, methods=["get"], url_path="templates")
    def templates(self, request):
        """Catálogo de modelos de estação (cozinha, bar, pizzaria…) para o onboarding."""
        return Response(STATION_TEMPLATES)

    @action(detail=False, methods=["post"], url_path="from-template")
    def from_template(self, request):
        """Cria uma estação + suas colunas de uma vez, a partir de um modelo."""
        template = TEMPLATES_BY_KEY.get(request.data.get("template"))
        if template is None:
            return Response({"template": "Modelo inválido."}, status=status.HTTP_400_BAD_REQUEST)

        account = getattr(request, "account", None)
        if account is None:
            return Response({"detail": "Contexto de conta é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

        restaurant = Restaurant.objects.filter(pk=request.data.get("restaurant"), account=account).first()
        if restaurant is None:
            return Response({"restaurant": "Selecione um restaurante válido."}, status=status.HTTP_400_BAD_REQUEST)

        name = (request.data.get("name") or template["name"]).strip()
        try:
            sla_minutes = int(request.data.get("sla_minutes") or 15)
        except (TypeError, ValueError):
            sla_minutes = 15
        # Setores: usa o que o formulário enviar; senão, o padrão do modelo.
        sectors = request.data.get("sectors")
        if not isinstance(sectors, list):
            sectors = template.get("sectors", [])

        with transaction.atomic():
            station = KdsStation.objects.create(
                account=account, restaurant=restaurant, name=name, sla_minutes=sla_minutes, sectors=sectors,
            )
            KdsColumn.objects.bulk_create([
                KdsColumn(
                    account=account, station=station, position=pos, name=col["name"],
                    color=col["color"], is_entry=col["is_entry"], is_done=col["is_done"],
                )
                for pos, col in enumerate(template["columns"])
            ])
        station = self.get_queryset().get(pk=station.pk)
        return Response(self.get_serializer(station).data, status=status.HTTP_201_CREATED)


class KdsColumnViewSet(BaseTenantViewSet):
    serializer_class = KdsColumnSerializer
    queryset = KdsColumn.objects.select_related("station").all()
    filterset_fields = ["station", "is_active"]
    ordering_fields = ["position", "name"]
    ordering = ["position"]
