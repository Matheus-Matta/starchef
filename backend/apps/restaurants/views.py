from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.limits import assert_can_create_restaurant
from apps.core.codes import barcode_data_uri, qr_data_uri
from apps.core.modules import MODULE_ENTREGA
from apps.core.viewsets import BaseTenantViewSet
from apps.realtime.events import broadcast_resource_event
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
from apps.restaurants.services import default_command_code, next_command_number, sync_branch_for_restaurant


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
    MAX_BULK_TABLES = 100

    @action(detail=False, methods=["post"], url_path="bulk-create")
    def bulk_create(self, request):
        """Cria um intervalo de mesas de uma vez (ex: mesa 1 a 40)."""
        account = getattr(request, "account", None)
        profile = getattr(request.user, "profile", None)

        sector_id = request.data.get("sector")
        if not sector_id:
            raise ValidationError({"sector": "Selecione o setor para criar mesas."})

        sector = TableSector.objects.filter(pk=sector_id, account=account).first()
        if not sector:
            raise ValidationError({"sector": "Setor não encontrado nesta conta."})

        # Dados antigos podiam guardar um setor do restaurante B com a filial
        # herdada do restaurante A. Corrige o vínculo antes de verificar/criar
        # mesas para que a numeração seja independente por restaurante.
        target_branch = sync_branch_for_restaurant(sector.restaurant)
        if sector.branch_id != target_branch.id:
            sector.branch = target_branch
            sector.updated_by = request.user
            sector.save(update_fields=["branch", "updated_by", "updated_at"])

        from apps.core.access import is_tenant_admin

        if profile and not is_tenant_admin(request.user):
            if profile.branch_id and sector.branch_id != profile.branch_id:
                raise ValidationError({"sector": "Setor fora do escopo do usuário."})
            if profile.restaurant_id and sector.restaurant_id != profile.restaurant_id:
                raise ValidationError({"sector": "Setor pertence a outro restaurante."})

        to_number = request.data.get("to_number")
        if to_number is None:
            raise ValidationError({"to_number": "Informe o número final do intervalo."})
        try:
            to_number = int(to_number)
            from_number = int(request.data.get("from_number") or 1)
        except (TypeError, ValueError):
            raise ValidationError({"detail": "from_number/to_number devem ser inteiros."})

        if from_number < 1 or to_number < from_number:
            raise ValidationError({"detail": "Intervalo inválido (from_number ≤ to_number, ambos ≥ 1)."})
        if to_number - from_number + 1 > self.MAX_BULK_TABLES:
            raise ValidationError({"detail": f"Máximo de {self.MAX_BULK_TABLES} mesas por lote."})

        existing = set(
            Table.all_objects.filter(
                restaurant=sector.restaurant,
                number__in=[str(n) for n in range(from_number, to_number + 1)],
            ).values_list("number", flat=True)
        )
        created = []
        for number_int in range(from_number, to_number + 1):
            number_str = str(number_int)
            if number_str in existing:
                continue
            created.append(
                Table(
                    account=account,
                    restaurant=sector.restaurant,
                    branch=target_branch,
                    sector=sector,
                    number=number_str,
                    code=number_str,
                    capacity=4,
                    created_by=request.user,
                    updated_by=request.user,
                )
            )
        Table.objects.bulk_create(created)
        if created:
            transaction.on_commit(
                lambda: broadcast_resource_event(
                    account.id,
                    resource="restaurants.table",
                    action="created",
                    restaurant_id=sector.restaurant_id,
                    branch_id=sector.branch_id,
                    changed_fields={"collection"},
                )
            )
        return Response(
            {"created": len(created), "skipped": len(existing), "from_number": from_number, "to_number": to_number},
            status=201,
        )

    @action(detail=True, methods=["post"], url_path="transfer-commands")
    @transaction.atomic
    def transfer_commands(self, request, pk=None):
        """Transfere TODAS as comandas desta mesa para outra."""
        from_table = Table.objects.select_for_update().get(pk=self.get_object().pk)
        to_table_id = request.data.get("to_table_id")

        if not to_table_id:
            raise ValidationError({"to_table_id": "Informe a mesa de destino."})

        to_table = self.get_queryset().select_for_update().filter(pk=to_table_id).first()
        if not to_table:
            raise ValidationError({"to_table_id": "Mesa destino não encontrada."})

        if from_table.id == to_table.id:
            raise ValidationError({"to_table_id": "A mesa de destino não pode ser a mesma de origem."})
        if to_table.status == Table.STATUS_CLEANING:
            raise ValidationError({"to_table_id": "A mesa de destino aguarda limpeza."})

        commands = list(from_table.active_commands.all())
        if not commands:
            raise ValidationError({"detail": "Não há comandas vinculadas a esta mesa para transferir."})

        from apps.orders.models import Order
        from apps.restaurants.models import CommandMovementLog

        logs = []
        for cmd in commands:
            cmd.current_table = to_table
            cmd.save(update_fields=["current_table", "updated_at"])
            if cmd.current_order_id:
                Order.objects.filter(
                    pk=cmd.current_order_id,
                    status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
                ).update(
                    table=to_table,
                    updated_by=request.user,
                    updated_at=timezone.now(),
                )
            logs.append(
                CommandMovementLog(
                    account=cmd.account,
                    restaurant=cmd.restaurant,
                    branch=cmd.branch,
                    command=cmd,
                    action=CommandMovementLog.ACTION_TRANSFERRED,
                    table=to_table,
                    from_table=from_table,
                    waiter=request.user,
                )
            )

        CommandMovementLog.objects.bulk_create(logs)

        to_table.status = Table.STATUS_OCCUPIED
        to_table.current_order_id = None
        to_table.save(update_fields=["status", "current_order_id", "updated_at"])

        from apps.orders.services import free_table_if_empty

        free_table_if_empty(from_table)

        return Response({"transferred": len(commands)})


class CommandViewSet(ScannableCodesMixin, BaseTenantViewSet):
    """Cadastro de comandas reutilizáveis (padrão self-service / Graal)."""

    serializer_class = CommandSerializer
    queryset = Command.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["status", "is_active"]
    search_fields = ["number", "code", "customer_name"]
    ordering_fields = ["number", "status", "updated_at"]
    MAX_BULK_COMMANDS = 200

    def destroy(self, request, *args, **kwargs):
        command = self.get_object()
        if command.status != Command.STATUS_FREE or command.current_order_id or command.current_table_id:
            raise ValidationError({"detail": "Comandas ocupadas não podem ser excluídas."})
        return super().destroy(request, *args, **kwargs)

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

    @action(detail=True, methods=["post"], url_path="link-table")
    @transaction.atomic
    def link_table(self, request, pk=None):
        """Vincula a comanda a uma mesa específica."""
        command = Command.objects.select_for_update().get(pk=self.get_object().pk)
        table_id = request.data.get("table_id")
        if not table_id:
            raise ValidationError({"table_id": "Informe a mesa para vincular a comanda."})

        table = (
            Table.objects.select_for_update()
            .filter(
                pk=table_id,
                account=command.account,
                restaurant=command.restaurant,
                branch=command.branch,
                is_active=True,
            )
            .first()
        )
        if not table:
            raise ValidationError({"table_id": "Mesa não encontrada nesta filial."})

        if command.current_table_id == table.id:
            return Response(self.get_serializer(command).data)
        if table.status == Table.STATUS_CLEANING:
            raise ValidationError({"table_id": "A mesa selecionada aguarda limpeza."})

        from apps.restaurants.models import CommandMovementLog

        old_table_id = command.current_table_id
        command.current_table = table
        command.save(update_fields=["current_table", "updated_at"])

        if command.current_order_id:
            from apps.orders.models import Order

            Order.objects.filter(
                pk=command.current_order_id,
                status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
            ).update(
                table=table,
                updated_by=request.user,
                updated_at=timezone.now(),
            )

        CommandMovementLog.objects.create(
            account=command.account,
            restaurant=command.restaurant,
            branch=command.branch,
            command=command,
            action=CommandMovementLog.ACTION_LINKED,
            table=table,
            from_table_id=old_table_id,
            waiter=request.user,
        )

        table.status = Table.STATUS_OCCUPIED
        table.current_order_id = None
        table.save(update_fields=["status", "current_order_id", "updated_at"])

        if old_table_id:
            from apps.orders.services import free_table_if_empty

            free_table_if_empty(Table.objects.get(pk=old_table_id))

        return Response(self.get_serializer(command).data)

    @action(detail=True, methods=["post"], url_path="unlink-table")
    @transaction.atomic
    def unlink_table(self, request, pk=None):
        """Desvincula a comanda da mesa atual."""
        command = Command.objects.select_for_update().get(pk=self.get_object().pk)
        if not command.current_table_id:
            return Response(self.get_serializer(command).data)

        old_table_id = command.current_table_id
        command.current_table = None
        command.save(update_fields=["current_table", "updated_at"])

        if command.current_order_id:
            from apps.orders.models import Order

            Order.objects.filter(
                pk=command.current_order_id,
                status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
            ).update(
                table=None,
                updated_by=request.user,
                updated_at=timezone.now(),
            )

        from apps.restaurants.models import CommandMovementLog

        CommandMovementLog.objects.create(
            account=command.account,
            restaurant=command.restaurant,
            branch=command.branch,
            command=command,
            action=CommandMovementLog.ACTION_UNLINKED,
            from_table_id=old_table_id,
            waiter=request.user,
        )

        from apps.orders.services import free_table_if_empty

        free_table_if_empty(Table.objects.get(pk=old_table_id))

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
            if (
                profile
                and profile.restaurant_id
                and not is_tenant_admin(request.user)
                and restaurant.id != profile.restaurant_id
            ):
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
        if to_number - from_number + 1 > self.MAX_BULK_COMMANDS:
            raise ValidationError({"detail": f"Máximo de {self.MAX_BULK_COMMANDS} comandas por lote."})

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
        if created:
            transaction.on_commit(
                lambda: broadcast_resource_event(
                    account.id,
                    resource="restaurants.command",
                    action="created",
                    restaurant_id=restaurant.id,
                    branch_id=getattr(profile, "branch_id", None),
                    changed_fields={"collection"},
                )
            )
        return Response(
            {"created": len(created), "skipped": len(existing), "from_number": from_number, "to_number": to_number},
            status=201,
        )

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    @transaction.atomic
    def bulk_delete(self, request):
        """Exclui um lote com uma única operação, sem rajada de conexões."""
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            raise ValidationError({"ids": "Informe uma lista não vazia de comandas."})
        ids = list(dict.fromkeys(str(value) for value in ids))
        if len(ids) > self.MAX_BULK_COMMANDS:
            raise ValidationError({"ids": f"Máximo de {self.MAX_BULK_COMMANDS} comandas por operação."})

        commands = self.filter_queryset(self.get_queryset()).filter(pk__in=ids)
        if commands.count() != len(ids):
            raise ValidationError({"ids": "Uma ou mais comandas não existem ou estão fora do seu acesso."})
        occupied = commands.exclude(
            status=Command.STATUS_FREE,
            current_order_id=None,
            current_table_id=None,
        ).count()
        if occupied:
            raise ValidationError({"ids": f"{occupied} comanda(s) estão ocupadas e não podem ser excluídas."})

        scopes = list(commands.values_list("account_id", "restaurant_id", "branch_id").distinct())
        now = timezone.now()
        deleted = commands.update(deleted_at=now, updated_at=now, updated_by=request.user)
        for account_id, restaurant_id, branch_id in scopes:
            transaction.on_commit(
                lambda account_id=account_id, restaurant_id=restaurant_id, branch_id=branch_id: (
                    broadcast_resource_event(
                        account_id,
                        resource="restaurants.command",
                        action="deleted",
                        restaurant_id=restaurant_id,
                        branch_id=branch_id,
                        changed_fields={"collection", "deleted_at"},
                    )
                )
            )
        return Response({"deleted": deleted}, status=200)

    @action(detail=False, methods=["post"], url_path="bulk-update")
    @transaction.atomic
    def bulk_update(self, request):
        """Atualiza o estado de várias comandas em uma única consulta."""
        ids = request.data.get("ids")
        changes = request.data.get("changes")
        if not isinstance(ids, list) or not ids:
            raise ValidationError({"ids": "Informe uma lista não vazia de comandas."})
        ids = list(dict.fromkeys(str(value) for value in ids))
        if len(ids) > self.MAX_BULK_COMMANDS:
            raise ValidationError({"ids": f"Máximo de {self.MAX_BULK_COMMANDS} comandas por operação."})
        if not isinstance(changes, dict) or set(changes) != {"is_active"} or not isinstance(changes["is_active"], bool):
            raise ValidationError({"changes": "A atualização em lote permite somente o campo is_active booleano."})

        commands = self.filter_queryset(self.get_queryset()).filter(pk__in=ids)
        if commands.count() != len(ids):
            raise ValidationError({"ids": "Uma ou mais comandas não existem ou estão fora do seu acesso."})
        if (
            changes["is_active"] is False
            and commands.exclude(
                status=Command.STATUS_FREE,
                current_order_id=None,
                current_table_id=None,
            ).exists()
        ):
            raise ValidationError({"ids": "Desvincule e encerre as comandas antes de desativá-las."})

        scopes = list(commands.values_list("account_id", "restaurant_id", "branch_id").distinct())
        now = timezone.now()
        updated = commands.update(
            is_active=changes["is_active"],
            updated_at=now,
            updated_by=request.user,
        )
        for account_id, restaurant_id, branch_id in scopes:
            transaction.on_commit(
                lambda account_id=account_id, restaurant_id=restaurant_id, branch_id=branch_id: (
                    broadcast_resource_event(
                        account_id,
                        resource="restaurants.command",
                        action="updated",
                        restaurant_id=restaurant_id,
                        branch_id=branch_id,
                        changed_fields={"collection", "is_active"},
                    )
                )
            )
        return Response({"updated": updated}, status=200)


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
