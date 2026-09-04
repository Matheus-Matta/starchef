from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Max, Min, Q, Sum
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import is_tenant_admin
from apps.core.codes import barcode_data_uri, qr_data_uri
from apps.core.modules import MODULE_LOGISTICA
from apps.core.viewsets import BaseTenantViewSet, ReadOnlyTenantViewSet
from apps.menu.models import Ingredient
from apps.stock.lots import (
    cancel_stock_entry,
    post_stock_entry,
    post_stock_exit,
    scan_exit_label,
    settings_for,
    suggest_exit_lots,
)
from apps.stock.models import (
    StockEntry,
    StockExit,
    StockLabelTemplate,
    StockLocation,
    StockLot,
    StockMovement,
    StockSettings,
    Supplier,
)
from apps.stock.serializers import (
    StockAllocationSerializer,
    StockEntrySerializer,
    StockExitSerializer,
    StockLabelTemplateSerializer,
    StockLocationSerializer,
    StockLotSerializer,
    StockMovementSerializer,
    StockSettingsSerializer,
    SupplierSerializer,
)


class StockLocationViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = StockLocationSerializer
    queryset = StockLocation.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["is_active"]
    search_fields = ["name"]


class SupplierViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["is_active"]
    search_fields = ["name", "legal_name", "tax_id", "contact_name", "email", "phone"]
    ordering_fields = ["name", "created_at", "updated_at"]
    ordering = ["name"]


class StockSettingsViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = StockSettingsSerializer
    queryset = StockSettings.objects.select_related("restaurant", "branch", "default_location").all()

    @action(detail=False, methods=["get"])
    def current(self, request):
        """A configuracao da conta, com os padroes quando ela nao existe.

        A tela precisa de algo para mostrar antes de alguem salvar qualquer
        coisa; devolver 404 obrigaria o frontend a repetir os padroes e os
        dois se desencontrariam na primeira mudanca de politica.
        """
        existing = self.filter_queryset(self.get_queryset()).first()
        if existing is not None:
            return Response(self.get_serializer(existing).data)

        defaults = settings_for(getattr(request, "account", None))
        data = self.get_serializer(defaults).data
        data["id"] = None
        return Response(data)


class StockLabelTemplateViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = StockLabelTemplateSerializer
    queryset = StockLabelTemplate.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["is_active", "code_type"]
    search_fields = ["name"]


class StockLotViewSet(ReadOnlyTenantViewSet):
    """Lotes sao consultados, nunca criados pela API.

    Um lote nasce da confirmacao de uma entrada — e so assim ele tem um
    movimento positivo explicando de onde veio o saldo.
    """

    required_module = MODULE_LOGISTICA
    serializer_class = StockLotSerializer
    queryset = StockLot.objects.select_related("restaurant", "branch", "ingredient", "location").all()
    filterset_fields = ["ingredient", "location", "status"]
    search_fields = ["code", "supplier_lot", "ingredient__name"]
    ordering_fields = ["expires_at", "entered_at", "quantity"]

    @action(detail=False, methods=["get"])
    def lookup(self, request):
        """Resolve o codigo de uma etiqueta lida — usada na conferencia."""
        code = str(request.query_params.get("code") or "").strip().upper()
        if not code:
            return Response({"detail": "Informe o codigo da etiqueta."}, status=400)
        lot = self.filter_queryset(self.get_queryset()).filter(code=code).first()
        if lot is None:
            return Response({"detail": f"Nenhum lote encontrado para {code}."}, status=404)
        return Response(self.get_serializer(lot).data)

    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        lot = self.get_object()
        lot.status = StockLot.STATUS_BLOCKED
        lot.updated_by = request.user
        lot.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(self.get_serializer(lot).data)

    @action(detail=True, methods=["post"])
    def unblock(self, request, pk=None):
        lot = self.get_object()
        lot.status = StockLot.STATUS_AVAILABLE if lot.quantity > 0 else StockLot.STATUS_DEPLETED
        lot.updated_by = request.user
        lot.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(self.get_serializer(lot).data)


class StockEntryViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = StockEntrySerializer
    queryset = (
        StockEntry.objects.select_related("restaurant", "branch", "location")
        .prefetch_related("items__ingredient", "items__supplier", "items__lots")
        .all()
    )
    filterset_fields = ["status", "location"]
    search_fields = ["document_number", "supplier"]
    ordering_fields = ["effective_date", "created_at"]

    @action(detail=True, methods=["post"])
    def post_entry(self, request, pk=None):
        entry = self.get_object()
        lots = post_stock_entry(entry=entry, user=request.user)
        entry.refresh_from_db()
        return Response(
            {
                "entry": self.get_serializer(entry).data,
                "lots": StockLotSerializer(lots, many=True).data,
            }
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        entry = self.get_object()
        cancel_stock_entry(entry=entry, user=request.user, reason=request.data.get("reason", ""))
        entry.refresh_from_db()
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=["get"])
    def labels(self, request, pk=None):
        """Os dados que a etiqueta imprime, ja expandidos por copia.

        A expansao acontece aqui, e nao no navegador, para que "reimprimir a
        linha 3" produza exatamente as mesmas etiquetas da primeira vez.
        """
        entry = self.get_object()
        template_id = request.query_params.get("template")
        template = None
        if template_id:
            template = StockLabelTemplate.objects.filter(pk=template_id).first()
        if template is None:
            config = settings_for(entry.account)
            template = config.default_label_template
        if template is None:
            template = StockLabelTemplate.objects.filter(is_active=True).first()

        use_qr = not template or template.code_type == StockLabelTemplate.CODE_QR
        only_items = request.query_params.getlist("item")
        labels = []
        for item in entry.items.select_related("ingredient").prefetch_related("lots"):
            if only_items and str(item.id) not in only_items:
                continue
            for lot in item.lots.all():
                # A imagem do codigo e gerada uma vez por LOTE e reaproveitada
                # nas copias: sao os mesmos bytes, e desenhar de novo a cada
                # etiqueta so multiplicaria o tamanho da resposta.
                code_uri = qr_data_uri(lot.code) if use_qr else barcode_data_uri(lot.code)
                copies = max(1, int(item.label_count or 1))
                for _ in range(copies):
                    labels.append(
                        {
                            "lot_id": str(lot.id),
                            "code": lot.code,
                            "code_uri": code_uri,
                            "ingredient_name": lot.ingredient.name,
                            "unit": lot.ingredient.unit,
                            "supplier_lot": lot.supplier_lot,
                            "entered_at": lot.entered_at,
                            "expires_at": lot.expires_at,
                            "quantity": lot.initial_quantity,
                            "location_name": lot.location.name,
                        }
                    )
        return Response(
            {
                "template": StockLabelTemplateSerializer(template).data if template else None,
                "labels": labels,
            }
        )


class StockExitViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = StockExitSerializer
    queryset = (
        StockExit.objects.select_related("restaurant", "branch", "location")
        .prefetch_related("items__ingredient", "items__allocations__lot")
        .all()
    )
    filterset_fields = ["status", "location", "exit_type"]
    search_fields = ["reason"]
    ordering_fields = ["effective_date", "created_at"]

    @action(detail=True, methods=["post"])
    def suggest_lots(self, request, pk=None):
        exit_document = self.get_object()
        shortages = suggest_exit_lots(exit_document=exit_document, user=request.user)
        exit_document.refresh_from_db()
        return Response({"exit": self.get_serializer(exit_document).data, "shortages": shortages})

    @action(detail=True, methods=["post"])
    def scan_label(self, request, pk=None):
        exit_document = self.get_object()
        allocation = scan_exit_label(
            exit_document=exit_document,
            code=request.data.get("code"),
            user=request.user,
            quantity=request.data.get("quantity"),
        )
        return Response(StockAllocationSerializer(allocation).data)

    @action(detail=True, methods=["post"])
    def post_exit(self, request, pk=None):
        exit_document = self.get_object()
        post_stock_exit(exit_document=exit_document, user=request.user)
        exit_document.refresh_from_db()
        return Response(self.get_serializer(exit_document).data)


class StockMovementViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = StockMovementSerializer
    queryset = StockMovement.objects.select_related(
        "restaurant", "branch", "ingredient", "location", "operator", "lot"
    ).all()
    filterset_fields = ["ingredient", "location", "movement_type", "lot"]
    ordering_fields = ["created_at", "quantity", "total_cost"]

    def perform_create(self, serializer):
        instance = serializer.save()
        if instance.movement_type == StockMovement.TYPE_IN and instance.unit_cost > 0:
            from apps.menu.services import update_ingredient_average_cost
            update_ingredient_average_cost(instance.ingredient, instance.quantity, instance.unit_cost)


def tenant_scope_filters(request):
    """Recorte de conta/restaurante/filial para consultas montadas na mao.

    As telas de relatorio agregam movimentos e lotes fora de um viewset, entao
    nao herdam o `TenantQuerySetMixin`. Sem conta no request nao ha o que
    responder — nem para superusuario, porque a API nunca consolida contas
    (ver TenantMiddleware.resolve_account); `account_id: None` devolve vazio.
    """
    account = getattr(request, "account", None)
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


def scoped_ingredients(filters):
    """Insumos visiveis no recorte — incluindo os compartilhados pela conta.

    Insumo tem `restaurant` opcional (e reutilizavel entre restaurantes), entao
    filtrar so pelo id do restaurante escondia justamente os que valem para
    todos — os mesmos que aparecem nos dropdowns da entrada e da saida.
    """
    if not filters.get("account_id"):
        return Ingredient.all_objects.none()
    queryset = Ingredient.all_objects.filter(
        account_id=filters["account_id"], deleted_at__isnull=True
    )
    if restaurant_id := filters.get("restaurant_id"):
        queryset = queryset.filter(Q(restaurant_id=restaurant_id) | Q(restaurant__isnull=True))
    if branch_id := filters.get("branch_id"):
        queryset = queryset.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))
    return queryset


class StockAlertView(APIView):
    """Return ingredients whose current stock balance is below their minimum_stock."""

    required_module = MODULE_LOGISTICA

    def get(self, request):
        filters = tenant_scope_filters(request)
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


class StockExpiryReportView(APIView):
    """Lotes vencidos e a vencer, agrupados por urgencia."""

    required_module = MODULE_LOGISTICA

    def get(self, request):
        today = timezone.localdate()
        horizon = int(request.query_params.get("days") or 30)
        lots = (
            StockLot.objects.filter(status=StockLot.STATUS_AVAILABLE, quantity__gt=0)
            .exclude(expires_at__isnull=True)
            .select_related("ingredient", "location")
            .order_by("expires_at")
        )
        rows = []
        for lot in lots:
            days = (lot.expires_at - today).days
            if days > horizon:
                continue
            rows.append(
                {
                    "lot_id": str(lot.id),
                    "code": lot.code,
                    "ingredient_name": lot.ingredient.name,
                    "unit": lot.ingredient.unit,
                    "location_name": lot.location.name,
                    "quantity": lot.quantity,
                    "expires_at": lot.expires_at,
                    "days_to_expiry": days,
                    "value_at_risk": (lot.quantity * lot.unit_cost).quantize(Decimal("0.01")),
                }
            )
        return Response({"today": today, "horizon_days": horizon, "lots": rows, "count": len(rows)})


class StockPositionView(APIView):
    """Posicao de estoque: um insumo por linha, com saldo, minimo e valor.

    O saldo sai do livro de movimentos, e nao da soma dos lotes: ha saldo que
    nunca passou por lote (ajuste manual, baixa de venda de insumo sem controle
    de validade) e uma tela que ignorasse esse saldo mostraria zerado um insumo
    que esta na prateleira. Os lotes entram so para a leitura de validade.
    """

    required_module = MODULE_LOGISTICA

    def get(self, request):
        filters = tenant_scope_filters(request)
        location_id = request.query_params.get("location") or None

        movements = StockMovement.objects.filter(**filters)
        lots = StockLot.objects.filter(**filters, quantity__gt=0).exclude(
            status__in=[StockLot.STATUS_DISCARDED, StockLot.STATUS_DEPLETED]
        )
        if location_id:
            movements = movements.filter(location_id=location_id)
            lots = lots.filter(location_id=location_id)

        balances = {}
        for row in movements.values("ingredient_id").annotate(
            balance=Sum("quantity"), last_movement_at=Max("created_at")
        ):
            balances[row["ingredient_id"]] = row

        by_location = defaultdict(list)
        for row in (
            movements.values("ingredient_id", "location_id", "location__name")
            .annotate(balance=Sum("quantity"))
            .order_by("location__name")
        ):
            # Local zerado nao e informacao: polui a linha do insumo com todos
            # os lugares por onde ele ja passou.
            if not row["balance"]:
                continue
            by_location[row["ingredient_id"]].append(
                {
                    "location_id": str(row["location_id"]),
                    "location_name": row["location__name"],
                    "balance": row["balance"],
                }
            )

        today = timezone.localdate()
        # `Min` ignora os lotes sem validade — o que sobra e exatamente a
        # validade mais proxima, que e a unica que a tela precisa mostrar.
        lot_info = {
            row["ingredient_id"]: row
            for row in lots.values("ingredient_id").annotate(
                lot_count=Count("id"), next_expiry=Min("expires_at")
            )
        }

        rows = []
        for ingredient in scoped_ingredients(filters).order_by("name"):
            movement = balances.get(ingredient.id) or {}
            balance = movement.get("balance") or Decimal("0")
            # Insumo inativo so aparece enquanto ainda houver saldo dele: ele
            # saiu do cardapio, mas continua ocupando prateleira.
            if not ingredient.is_active and not balance:
                continue
            minimum = ingredient.minimum_stock
            if balance <= 0:
                situation = "out"
            elif minimum is not None and balance < minimum:
                situation = "low"
            else:
                situation = "ok"
            next_expiry = (lot_info.get(ingredient.id) or {}).get("next_expiry")
            rows.append(
                {
                    "ingredient_id": str(ingredient.id),
                    "ingredient_name": ingredient.name,
                    "unit": ingredient.unit,
                    "is_active": ingredient.is_active,
                    "balance": balance,
                    "minimum_stock": minimum,
                    "average_cost": ingredient.average_cost,
                    "stock_value": (balance * ingredient.average_cost).quantize(Decimal("0.01")),
                    "situation": situation,
                    "locations": by_location.get(ingredient.id, []),
                    "lot_count": (lot_info.get(ingredient.id) or {}).get("lot_count", 0),
                    "next_expiry": next_expiry,
                    "expired": bool(next_expiry and next_expiry < today),
                    "last_movement_at": movement.get("last_movement_at"),
                }
            )

        totals = {
            "ingredients": len(rows),
            "low": sum(1 for row in rows if row["situation"] == "low"),
            "out": sum(1 for row in rows if row["situation"] == "out"),
            "expired": sum(1 for row in rows if row["expired"]),
            "stock_value": sum((row["stock_value"] for row in rows), Decimal("0")),
        }
        return Response({"positions": rows, "totals": totals, "count": len(rows)})
