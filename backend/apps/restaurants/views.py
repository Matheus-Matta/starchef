from decimal import Decimal

import django_filters
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

from apps.accounts.limits import assert_can_create_restaurant
from apps.core.codes import barcode_data_uri, qr_data_uri
from apps.orders.command_billing import em_uso_subquery
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
from apps.restaurants.services import (
    assert_table_accepts_commands,
    default_command_code,
    next_command_number,
    sync_branch_for_restaurant,
)


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
    queryset = Restaurant.all_objects.select_related("logo_image").all()
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
    queryset = Table.objects.select_related("restaurant", "branch", "sector").prefetch_related("active_commands").all()
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
        restaurant_id = request.data.get("restaurant")
        if restaurant_id and str(sector.restaurant_id) != str(restaurant_id):
            raise ValidationError({"sector": "O setor não pertence ao restaurante selecionado."})

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
        except (TypeError, ValueError) as exc:
            raise ValidationError({"detail": "from_number/to_number devem ser inteiros."}) from exc

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
        assert_table_accepts_commands(to_table, adding=len(commands))

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


class CommandFilterSet(django_filters.FilterSet):
    """`?status=free|occupied` continua funcionando — sem coluna `status`.

    "Em uso" virou cálculo: é ter anotação pendente com valor. O filtro
    pergunta isso ao banco com `Exists`, numa subconsulta, em vez de ler uma
    coluna que alguém precisava lembrar de manter em dia.

    O nome e os valores do parâmetro são os de antes de propósito: o PDV, o
    app do garçom e o painel já mandam `?status=occupied`, e trocar o contrato
    obrigaria os três a atualizar no mesmo dia.
    """

    status = django_filters.ChoiceFilter(
        choices=Command.STATUS_CHOICES, method="filtra_por_uso"
    )

    class Meta:
        model = Command
        fields = ["is_active"]

    def filtra_por_uso(self, queryset, name, value):
        from apps.orders.command_billing import em_uso_subquery

        anotado = queryset.annotate(tem_pendente=em_uso_subquery())
        return anotado.filter(tem_pendente=value == Command.STATUS_OCCUPIED)


class CommandViewSet(ScannableCodesMixin, BaseTenantViewSet):
    """Cadastro de comandas reutilizáveis (padrão self-service / Graal)."""

    serializer_class = CommandSerializer

    # "Em uso" é ter anotação PENDENTE, e a grade precisa disso em TODA linha.
    # Contado aqui, numa consulta só, e não por cartão: uma tela com duzentas
    # comandas faria duzentas idas ao banco só para pintar o selo de estado.
    queryset = (
        Command.objects.select_related("restaurant", "branch")
        .annotate(
            # Conta só o que TEM VALOR. Um cartão cujos pendentes são todos
            # cortesia ou cancelados não tem conta nenhuma, e pintá-lo de
            # ocupado manda o operador procurar o que não existe.
            pendentes=Count(
                "command_items",
                filter=Q(command_items__command_status="pending")
                & ~Q(command_items__status__in=["cancelled", "comped"]),
                distinct=True,
            ),
            pendente_total=Coalesce(
                Sum(
                    "command_items__total_price",
                    filter=Q(command_items__command_status="pending")
                    & ~Q(command_items__status__in=["cancelled", "comped"]),
                ),
                Decimal("0.00"),
            ),
        )
        .all()
    )
    filterset_class = CommandFilterSet
    search_fields = ["number", "code", "customer_name"]
    # `status` saiu da ordenação: não há coluna para o banco ordenar. Quem
    # quer os ocupados primeiro filtra por `status=occupied`.
    ordering_fields = ["number", "updated_at"]
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

    @action(detail=True, methods=["get"], url_path="items")
    def items(self, request, pk=None):
        """O que esta comanda tem AGORA — e, com `history=1`, o que ela já teve.

        As duas perguntas são diferentes, e misturá-las faz o cartão
        reutilizado reaparecer cheio com a conta do cliente anterior. "Agora"
        são as anotações PENDENTES; o histórico é tudo, sem filtro de estado.
        """
        from apps.orders.command_items import history_items_of_command, open_items_of_command
        from apps.orders.serializers import CommandItemSerializer

        command = self.get_object()
        historico = str(request.query_params.get("history") or "").lower() in {"1", "true", "yes"}
        itens = (
            history_items_of_command(command.pk) if historico else open_items_of_command(command.pk)
        )
        return Response(
            {
                "command": self.get_serializer(command).data,
                "history": historico,
                "items": CommandItemSerializer(itens, many=True).data,
            }
        )

    @items.mapping.post
    def launch_item(self, request, pk=None):
        """Anota um consumo NA COMANDA. Nenhum pedido é aberto.

        É o lançamento do garçom e o do balcão na tela de comandas: o cartão é
        um bloco de notas, e o pedido só nasce no caixa.
        """
        from apps.orders.command_items import launch_item
        from apps.orders.serializers import CommandItemSerializer
        command = self.get_object()
        if not request.data.get("product"):
            return Response(
                {"detail": "Selecione o produto a lançar na comanda."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            item = launch_item(
                command=command,
                product=request.data["product"],
                user=request.user,
                quantity=request.data.get("quantity", 1),
                unit_price=request.data.get("unit_price"),
                customer_note=request.data.get("customer_note") or "",
                variations=request.data.get("variations") or [],
                addons=request.data.get("addons") or [],
            )
        except ValidationError as exc:
            detalhe = getattr(exc, "messages", None) or [str(exc)]
            return Response({"detail": " ".join(detalhe)}, status=400)
        return Response(CommandItemSerializer(item).data, status=201)

    @action(detail=True, methods=["post"], url_path="send-to-kitchen")
    def send_to_kitchen(self, request, pk=None):
        """Manda a rodada pendente desta comanda para a produção."""
        from apps.orders.command_kitchen import send_command_to_kitchen

        command = self.get_object()
        try:
            lote = send_command_to_kitchen(
                command,
                request.user,
                client_batch_serial=request.data.get("client_batch_serial"),
                offline_printed=bool(request.data.get("offline_printed")),
            )
        except ValidationError as exc:
            detalhe = getattr(exc, "messages", None) or [str(exc)]
            return Response({"detail": " ".join(detalhe)}, status=400)
        return Response(
            {"batch": str(lote.id), "batch_number": lote.batch_number},
            status=200,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"items/(?P<item_pk>[^/.]+)/void",
    )
    def void_item(self, request, pk=None, item_pk=None):
        """Cancela uma anotação. Ela sai da comanda como PERDA."""
        from apps.orders.command_kitchen import void_command_item
        from apps.orders.models import CommandItem

        command = self.get_object()
        item = CommandItem.objects.filter(pk=item_pk, command=command).first()
        if item is None:
            return Response({"detail": "Item não encontrado nesta comanda."}, status=404)
        # Passada a janela de tempo do restaurante, cancelar exige quem
        # responde. É o mesmo gesto do pedido, com a mesma credencial.
        from apps.orders.item_cancellation import CancelamentoBloqueado
        from apps.orders.views import _can_authorize_cancellation

        authorized, authorizer, _how = _can_authorize_cancellation(
            request, command.restaurant, command.account_id
        )
        try:
            void_command_item(
                item,
                user=request.user,
                reason=request.data.get("reason") or "",
                authorized=authorized,
                authorized_by=authorizer,
            )
        except CancelamentoBloqueado as exc:
            from apps.core.exceptions import CancelBlocked

            raise CancelBlocked(" ".join(exc.messages)) from exc
        except ValidationError as exc:
            detalhe = getattr(exc, "messages", None) or [str(exc)]
            return Response({"detail": " ".join(detalhe)}, status=400)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="receipt")
    def receipt(self, request, pk=None):
        """Imprime a conferência DESTA comanda.

        É o papel que o caixa entrega ao cliente que pergunta "e a comanda 13,
        quanto deu?" dentro de uma mesa que vai pagar junto. **Não é documento
        fiscal**, e o cupom diz isso: a nota é uma só, do pedido que cobrar.
        """
        from apps.printers.command_receipt import register_command_receipt
        from apps.printers.serializers import PrintJobSerializer

        try:
            job, data = register_command_receipt(command=self.get_object(), user=request.user)
        except ValidationError as exc:
            detalhe = getattr(exc, "messages", None) or [str(exc)]
            return Response({"detail": " ".join(detalhe)}, status=400)
        return Response(
            {
                "print_job": PrintJobSerializer(job, context={"request": request}).data,
                "total": str(data["total"]),
            },
            status=201,
        )

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
                is_active=True,
            )
            .first()
        )
        if not table:
            raise ValidationError({"table_id": "Mesa não encontrada neste restaurante."})

        # A mesa é a fonte de verdade da filial do vínculo. Isso repara tanto
        # comandas antigas com filial herdada de outra unidade quanto bases que
        # ainda possuem mais de uma filial histórica no mesmo restaurante.
        if command.branch_id != table.branch_id:
            command.branch = table.branch
            command.updated_by = request.user
            command.save(update_fields=["branch", "updated_by", "updated_at"])

        if command.current_table_id == table.id:
            return Response(self.get_serializer(command).data)
        if table.status == Table.STATUS_CLEANING:
            raise ValidationError({"table_id": "A mesa selecionada aguarda limpeza."})
        assert_table_accepts_commands(table, exclude_command_ids=[command.pk])

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

            free_table_if_empty(Table.objects.filter(pk=old_table_id).first())

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

        free_table_if_empty(Table.objects.filter(pk=old_table_id).first())

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
        target_branch = sync_branch_for_restaurant(restaurant)

        to_number = request.data.get("to_number")
        if to_number is None:
            raise ValidationError({"to_number": "Informe o número final do intervalo."})
        try:
            to_number = int(to_number)
            from_number = int(request.data.get("from_number") or next_command_number(restaurant))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"detail": "from_number/to_number devem ser inteiros."}) from exc
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
                    branch=target_branch,
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
                    branch_id=target_branch.id,
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
        # "Ocupada" é ter o que cobrar. A subconsulta pergunta isso ao banco
        # para todas de uma vez — `get_queryset` reconstrói a consulta a partir
        # do model e não herda anotação declarada na classe.
        occupied = (
            commands.annotate(tem_pendente=em_uso_subquery())
            .exclude(tem_pendente=False, current_order_id=None, current_table_id=None)
            .count()
        )
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
            and commands.annotate(tem_pendente=em_uso_subquery())
            .exclude(tem_pendente=False, current_order_id=None, current_table_id=None)
            .exists()
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
