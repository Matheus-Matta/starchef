from django.core.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.limits import assert_can_create_restaurant
from apps.core.codes import barcode_data_uri, qr_data_uri
from apps.core.modules import MODULE_ENTREGA
from apps.core.viewsets import BaseTenantViewSet
from apps.restaurants.models import Branch, Command, DeliveryZone, Deliveryman, Restaurant, Table, TableSector
from apps.restaurants.serializers import (
    BranchSerializer,
    CommandSerializer,
    DeliveryZoneSerializer,
    DeliverymanSerializer,
    RestaurantSerializer,
    TableSectorSerializer,
    TableSerializer,
)
from apps.restaurants.services import default_command_code, next_command_number


def _codes_payload(obj):
    """QR + código de barras (data-URI) do código escaneável do objeto."""
    code = obj.code or ""
    return {"code": code, "qr_uri": qr_data_uri(code), "barcode_uri": barcode_data_uri(code)}


class ScannableCodesMixin:
    """Ações de códigos escaneáveis (QR/barcode) para recursos com campo `code`."""

    @action(detail=True, methods=["get"])
    def codes(self, request, pk=None):
        """QR + código de barras do item (para exibir/imprimir)."""
        return Response(_codes_payload(self.get_object()))

    @action(detail=False, methods=["post"], url_path="codes-batch")
    def codes_batch(self, request):
        """Gera as etiquetas de vários itens de uma vez (impressão em lote).

        Body: {"ids": [...], "kind": "qr" | "barcode"}. Retorna, na ordem por número,
        `{id, number, code, uri}` — uma única requisição para a folha de etiquetas.
        """
        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids:
            raise ValidationError({"ids": "Informe a lista de ids a imprimir."})
        if len(ids) > 500:
            raise ValidationError({"ids": "Máximo de 500 etiquetas por impressão."})
        kind = "barcode" if request.data.get("kind") == "barcode" else "qr"
        make = barcode_data_uri if kind == "barcode" else qr_data_uri

        objs = self.filter_queryset(self.get_queryset()).filter(pk__in=ids)
        items = [
            {"id": str(obj.id), "number": obj.number, "code": obj.code or "", "uri": make(obj.code or "")}
            for obj in sorted(objs, key=lambda o: (str(o.number).zfill(12), str(o.number)))
        ]
        return Response({"kind": kind, "items": items})


class RestaurantViewSet(BaseTenantViewSet):
    serializer_class = RestaurantSerializer
    queryset = Restaurant.all_objects.all()
    search_fields = ["trade_name", "legal_name", "cnpj"]
    ordering_fields = ["trade_name", "created_at"]

    def perform_create(self, serializer):
        # Aplica o limite de restaurantes da conta antes de criar (superadmin isento).
        if not self.request.user.is_superuser:
            assert_can_create_restaurant(getattr(self.request, "account", None))
        super().perform_create(serializer)

    @action(detail=True, methods=["get"], url_path="cash-auth")
    def cash_auth(self, request, pk=None):
        """Entrega o HASH da senha de ações do caixa para o app guardar e
        verificar OFFLINE (o texto puro nunca sai do servidor). Restrito ao
        escopo de tenant do usuário (permissões de objeto)."""
        restaurant = self.get_object()
        password_hash = restaurant.cash_action_password or None
        return Response(
            {
                "algorithm": password_hash.split("$", 1)[0] if password_hash else None,
                "has_password": bool(password_hash),
                "password_hash": password_hash,
            }
        )


class BranchViewSet(BaseTenantViewSet):
    serializer_class = BranchSerializer
    queryset = Branch.objects.select_related("restaurant").all()
    filterset_fields = ["is_active"]
    search_fields = ["name", "cnpj"]
    ordering_fields = ["name", "created_at"]


class TableSectorViewSet(BaseTenantViewSet):
    serializer_class = TableSectorSerializer
    queryset = TableSector.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["is_active"]
    search_fields = ["name"]


class TableViewSet(ScannableCodesMixin, BaseTenantViewSet):
    serializer_class = TableSerializer
    queryset = Table.objects.select_related("restaurant", "branch", "sector").all()
    filterset_fields = ["sector", "status", "is_active"]
    search_fields = ["number", "code"]
    ordering_fields = ["number", "status", "updated_at"]


class CommandViewSet(ScannableCodesMixin, BaseTenantViewSet):
    """Cadastro de comandas reutilizáveis (padrão self-service / Graal)."""

    serializer_class = CommandSerializer
    queryset = Command.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["status", "is_active"]
    search_fields = ["number", "code", "customer_name"]
    ordering_fields = ["number", "status", "updated_at"]

    @action(detail=False, methods=["get"], url_path="by-code")
    def by_code(self, request):
        """Resolve um código escaneado no PDV → comanda (habilita o scan futuro)."""
        code = (request.query_params.get("code") or "").strip()
        if not code:
            return Response({"detail": "Informe o parâmetro 'code'."}, status=400)
        command = self.get_queryset().filter(code=code).first()
        if not command:
            return Response({"detail": "Comanda não encontrada."}, status=404)
        return Response(self.get_serializer(command).data)

    def _resolve_bulk_restaurant(self, request, account, profile):
        """Restaurante do lote: id explícito (corpo/param) → perfil. Valida escopo."""
        from apps.core.access import is_tenant_admin

        restaurant_id = request.data.get("restaurant") or request.query_params.get("restaurant")
        if restaurant_id:
            restaurant = Restaurant.objects.filter(pk=restaurant_id, account=account).first()
            if restaurant is None:
                raise ValidationError({"restaurant": "Restaurante não encontrado nesta conta."})
            # Usuário não-admin só cria no próprio restaurante.
            if profile and profile.restaurant_id and not is_tenant_admin(request.user) and restaurant.id != profile.restaurant_id:
                raise ValidationError({"restaurant": "Restaurante fora do escopo do usuário."})
            return restaurant
        restaurant = getattr(profile, "restaurant", None)
        if restaurant is None:
            raise ValidationError({"restaurant": "Selecione o restaurante para criar comandas em lote."})
        return restaurant

    @action(detail=False, methods=["post"], url_path="bulk-create")
    def bulk_create(self, request):
        """Cria um intervalo de comandas de uma vez (registro rápido de cartões).

        Body: {"restaurant": "<id>", "from_number": 1, "to_number": 200}. `restaurant`
        e `from_number` são opcionais (perfil / próximo número). Pula números já
        existentes no restaurante.
        """
        account = getattr(request, "account", None)
        profile = getattr(request.user, "profile", None)
        restaurant = self._resolve_bulk_restaurant(request, account, profile)

        to_number = request.data.get("to_number")
        if to_number is None:
            raise ValidationError({"to_number": "Informe o número final do intervalo."})
        try:
            to_number = int(to_number)
            from_number = int(request.data.get("from_number") or next_command_number(restaurant))
        except (TypeError, ValueError):
            raise ValidationError({"detail": "from_number/to_number devem ser inteiros."})
        if from_number < 1 or to_number < from_number:
            raise ValidationError({"detail": "Intervalo inválido (from_number ≤ to_number, ambos ≥ 1)."})
        if to_number - from_number + 1 > 1000:
            raise ValidationError({"detail": "Máximo de 1000 comandas por lote."})

        existing = set(
            Command.all_objects.filter(restaurant=restaurant, number__range=(from_number, to_number)).values_list(
                "number", flat=True
            )
        )
        created = []
        for number in range(from_number, to_number + 1):
            if number in existing:
                continue
            created.append(
                Command(
                    account=account,
                    restaurant=restaurant,
                    branch=getattr(profile, "branch", None),
                    number=number,
                    code=default_command_code(number),
                    created_by=request.user,
                    updated_by=request.user,
                )
            )
        Command.objects.bulk_create(created)
        return Response(
            {"created": len(created), "skipped": len(existing), "from_number": from_number, "to_number": to_number},
            status=201,
        )


class DeliveryZoneViewSet(BaseTenantViewSet):
    required_module = MODULE_ENTREGA  # gestao logistica de delivery
    serializer_class = DeliveryZoneSerializer
    queryset = DeliveryZone.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["is_active"]
    search_fields = ["name"]
    ordering_fields = ["min_radius_km", "delivery_fee"]


class DeliverymanViewSet(BaseTenantViewSet):
    required_module = MODULE_ENTREGA  # gestao logistica de delivery
    serializer_class = DeliverymanSerializer
    queryset = Deliveryman.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["vehicle_type", "is_active"]
    search_fields = ["name", "phone"]
