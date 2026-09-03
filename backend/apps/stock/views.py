from decimal import Decimal

from django.db.models import Sum
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import is_tenant_admin
from apps.core.modules import MODULE_LOGISTICA
from apps.core.viewsets import BaseTenantViewSet
from apps.stock.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    InventoryLot,
    StockLocation,
    StockMovement,
)
from apps.stock.serializers import (
    GoodsReceiptSerializer,
    InventoryLotSerializer,
    StockLocationSerializer,
    StockMovementSerializer,
)


class StockLocationViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = StockLocationSerializer
    queryset = StockLocation.objects.select_related("restaurant", "branch", "parent_location").all()
    filterset_fields = ["is_active", "location_type"]
    search_fields = ["name", "description"]


class GoodsReceiptViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = GoodsReceiptSerializer
    queryset = (
        GoodsReceipt.objects
        .select_related("restaurant", "branch", "invoice", "received_by")
        .prefetch_related("items__product")
        .all()
    )
    filterset_fields = ["status", "invoice"]
    search_fields = ["receipt_number", "invoice__number", "invoice__supplier_name", "notes"]
    ordering_fields = ["received_at"]
    ordering = ["-received_at"]


class InventoryLotViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = InventoryLotSerializer
    queryset = (
        InventoryLot.objects
        .select_related("restaurant", "branch", "product", "location", "nfe", "receipt")
        .all()
    )
    filterset_fields = ["product", "location", "status"]
    search_fields = ["lot_number", "product__name", "supplier_name", "supplier_cnpj"]
    ordering_fields = ["expiration_date", "received_at", "available_quantity"]
    ordering = ["expiration_date", "received_at"]


class StockMovementViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = StockMovementSerializer
    queryset = (
        StockMovement.objects
        .select_related(
            "restaurant",
            "branch",
            "product",
            "ingredient",
            "location",
            "operator",
            "inventory_lot",
            "nfe",
        )
        .all()
    )
    filterset_fields = ["product", "ingredient", "location", "movement_type"]
    search_fields = ["product__name", "ingredient__name", "reason", "inventory_lot__lot_number"]
    ordering_fields = ["created_at", "quantity", "total_cost"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        instance = serializer.save()
        # Atualização de custo médio para produto
        if instance.product and instance.quantity > 0 and instance.unit_cost > 0:
            from apps.inbound_nfe.services.receiving import update_product_average_cost
            update_product_average_cost(instance.product, instance.quantity, instance.unit_cost)
        elif instance.ingredient and instance.quantity > 0 and instance.unit_cost > 0:
            from apps.menu.services import update_ingredient_average_cost
            update_ingredient_average_cost(instance.ingredient, instance.quantity, instance.unit_cost)


class StockAlertView(APIView):
    """Return ingredients whose current stock balance is below their minimum_stock."""

    required_module = MODULE_LOGISTICA

    def _tenant_filter(self, request):
        account = getattr(request, "account", None)
        # Sem conta no request não há alerta — nem para superusuário (a API
        # nunca consolida contas; ver TenantMiddleware.resolve_account).
        if not account:
            return {"account_id": None}
        filters = {"account_id": account.id}
        if is_tenant_admin(request.user):
            if restaurant_id := request.query_params.get("restaurant"):
                filters["restaurant_id"] = restaurant_id
            if branch_id := request.query_params.get("branch"):
                filters["branch_id"] = branch_id
            return filters
        profile = getattr(request.user, "profile", None)
        if not profile or not profile.restaurant_id:
            return {"account_id": None}
        filters["restaurant_id"] = profile.restaurant_id
        if profile.branch_id:
            filters["branch_id"] = profile.branch_id
        return filters

    def get(self, request):
        filters = self._tenant_filter(request)
        balances = (
            StockMovement.objects.filter(**filters)
            .values("ingredient_id", "ingredient__name", "ingredient__unit", "ingredient__minimum_stock")
            .annotate(balance=Sum("quantity"))
        )
        alerts = [
            {
                "ingredient_id": str(row["ingredient_id"]),
                "ingredient_name": row["ingredient__name"],
                "unit": row["ingredient__unit"],
                "balance": row["balance"] or Decimal("0"),
                "minimum_stock": row["ingredient__minimum_stock"],
            }
            for row in balances
            if (row["balance"] or Decimal("0")) < (row["ingredient__minimum_stock"] or Decimal("0"))
        ]
        alerts.sort(key=lambda r: r["balance"])
        return Response({"alerts": alerts, "count": len(alerts)})

