import django_filters
from apps.core.periodo import inicio_do_dia
from django.db.models import Q
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.requests import required_field
from apps.core.viewsets import ReadOnlyTenantViewSet
from apps.menu.models import Product
from apps.orders.models import Order, OrderItem
from apps.orders.serializers import OrderItemSerializer, OrderSerializer
from apps.orders.services import update_order_item_status
from .models import KdsColumn, KdsItemPosition, KdsStation
from .rules import apply_station_rules, move_position, regras_utilizaveis

# Pedidos sem producao possivel: saem do KDS. PAGO nao entra aqui de proposito
# — o caixa cobra assim que manda os itens para a cozinha, entao tirar o pago do
# quadro esconderia comida que ainda esta sendo preparada.
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
        .distinct()
    )
    filterset_fields = ["status", "production_status", "order_type", "items__production_sector"]
    ordering_fields = ["opened_at", "sequence"]

    def list(self, request, *args, **kwargs):
        from apps.orders.services import liberar_rodadas_vencidas_na_leitura

        account = getattr(request, "account", None)
        if account is not None:
            liberar_rodadas_vencidas_na_leitura(account.id)
        return super().list(request, *args, **kwargs)


class KitchenItemFilter(django_filters.FilterSet):
    """Filtro do KDS: setor/status + intervalo de datas (por data de lançamento).

    O dia vira INTERVALO de instantes, e não `launched_at__date`: a função de
    data aplicada na coluna impedia o Postgres de usar índice, e cada leitura
    do quadro (a cada poucos segundos, por tela de KDS) varria a tabela de
    itens inteira — que só cresce, dia após dia.
    """

    launched_after = django_filters.DateFilter(method="_a_partir_de")
    launched_before = django_filters.DateFilter(method="_ate")

    def _a_partir_de(self, queryset, name, value):
        return queryset.filter(launched_at__gte=inicio_do_dia(value))

    def _ate(self, queryset, name, value):
        from datetime import timedelta

        return queryset.filter(launched_at__lt=inicio_do_dia(value + timedelta(days=1)))

    class Meta:
        model = OrderItem
        fields = ["production_sector", "status"]


class KitchenItemViewSet(ReadOnlyTenantViewSet):
    serializer_class = OrderItemSerializer
    queryset = (
        OrderItem.objects.select_related(
            "restaurant",
            "branch",
            "order__table",
            "order__command",
            # A produção é lida da ORIGEM: sem estes dois, cada card do quadro
            # faria uma consulta a mais para descobrir de que comanda ele é.
            "command",
            "product",
            "batch",
        )
        .prefetch_related("addons", "kds_positions")
        .all()
    )
    filterset_class = KitchenItemFilter
    ordering_fields = ["launched_at", "ready_at", "sent_to_kitchen_at"]

    def list(self, request, *args, **kwargs):
        from apps.orders.services import liberar_rodadas_vencidas_na_leitura

        account = getattr(request, "account", None)
        if account is not None:
            liberar_rodadas_vencidas_na_leitura(account.id)
        station_id = request.query_params.get("station")
        if not station_id:
            return super().list(request, *args, **kwargs)
        station = KdsStation.objects.filter(pk=station_id, account=account, is_active=True).first()
        if station is None:
            return Response({"detail": "Estação KDS inválida."}, status=status.HTTP_400_BAD_REQUEST)
        queryset = self.filter_queryset(self.get_queryset())
        visible_ids = apply_station_rules(list(queryset), station, request.user)
        queryset = queryset.filter(pk__in=visible_ids)
        page = self.paginate_queryset(queryset)
        context = {**self.get_serializer_context(), "kds_station_id": station.id}
        serializer = self.get_serializer(page if page is not None else queryset, many=True, context=context)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    def get_queryset(self):
        # O KDS mostra só produto por UNIDADE: o prato por peso já está servido
        # (ver `orders/weighed_production.py`). O filtro também tira da tela os
        # itens por peso que já estavam "enviados" antes dessa regra.
        return self._por_estado(super().get_queryset().exclude(product__pricing_unit=Product.PRICING_KG))

    def _por_estado(self, queryset):
        # Quadros comuns ocultam cancelados. A cozinha conserva somente itens
        # que chegaram à produção para mostrar o cancelamento e seu motivo.
        # Pedidos pagos seguem visíveis enquanto a cozinha prepara o item.
        station_id = self.request.query_params.get("station")
        if station_id:
            station = KdsStation.objects.filter(
                pk=station_id, account=getattr(self.request, "account", None), is_active=True
            ).first()
        else:
            station = None
        if station:
            if any(rule.get("id") == "move-cancelled" and rule.get("enabled", True) for rule in regras_utilizaveis(station)):
                return queryset.filter(
                    (Q(status__in=_ACTIVE_ITEM_STATUSES) & ~Q(order__status__in=_INACTIVE_ORDER_STATUSES)) |
                    (Q(status=OrderItem.STATUS_CANCELLED, sent_to_kitchen_at__isnull=False) &
                     ~Q(order__status=Order.STATUS_REFUNDED))
                )
        return queryset.filter(status__in=_ACTIVE_ITEM_STATUSES).exclude(order__status__in=_INACTIVE_ORDER_STATUSES)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        try:
            item = update_order_item_status(
                self.get_object(),
                required_field(request, "status", "Informe o novo status do item."),
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

        if column and column.station.restaurant_id != item.restaurant_id:
            return Response({"detail": "A coluna não pertence ao restaurante do item."}, status=status.HTTP_400_BAD_REQUEST)

        if column and any(
            rule.get("id") == "move-cancelled" and str(rule.get("target_column")) == str(column.id)
            for rule in regras_utilizaveis(column.station)
        ):
            return Response(
                {"detail": "Cancele o item no pedido, informando o motivo; o KDS o moverá automaticamente."},
                status=status.HTTP_409_CONFLICT,
            )

        if column:
            entry = column.station.columns.filter(is_active=True, is_entry=True).first()
            entry = entry or column.station.columns.filter(is_active=True).order_by("position").first() or column
            position, _ = KdsItemPosition.objects.get_or_create(
                station=column.station,
                item=item,
                defaults={
                    "account": account, "column": entry,
                    "created_by": request.user, "updated_by": request.user,
                },
            )
            try:
                item = move_position(position, column, item, request.user)
            except ValidationError as exc:
                return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        else:
            item.kds_column = None
            item.save(update_fields=["kds_column", "updated_at"])
        return Response(self.get_serializer(item).data)


# Reexporta para preservar os imports públicos usados pelo router.
from .station_views import KdsColumnViewSet, KdsStationViewSet  # noqa: E402,F401
