from decimal import InvalidOperation

import django_filters
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import CancelBlocked
from apps.core.requests import required_field
from apps.core.viewsets import BaseTenantViewSet
from apps.core.access import is_tenant_admin
from apps.core.permissions import effective_permission_codes
from apps.menu.models import Product
from apps.orders.command_billing import attach_commands_to_order, detach_commands_from_order
from apps.orders.create_with_item_payload import build_first_item_data
from apps.orders.item_cancellation import CancelamentoBloqueado
from apps.orders.models import Order, OrderBatch, OrderItem
from apps.printers.models import ScaleReading
from apps.orders.serializers import OrderBatchSerializer, OrderItemSerializer, OrderSerializer
from apps.orders.services import (
    add_order_item,
    cancel_order,
    close_order,
    comp_order_item,
    create_order,
    create_order_with_item,
    recalculate_order,
    send_order_to_kitchen,
    set_order_item_quantity,
    update_order_item_status,
    void_order_item,
)
from apps.restaurants.models import Command

User = get_user_model()


def _can_authorize_cancellation(request, restaurant, account_id):
    """Valida a autorização no mesmo request que altera o pedido.

    A senha nunca entra na fila offline: cancelamento exige resposta imediata
    do servidor, evitando guardar credenciais em texto puro no terminal.

    Validar AQUI, e nao emitir um token para usar depois, e o que torna a
    autorizacao naturalmente de uso unico e presa a esta operacao: nao existe
    janela em que ela possa ser reaproveitada para outra coisa, nem estado a
    expirar. Quem autoriza tambem nao vira administrador da sessao — a
    permissao dele vale para este request e acaba com ele.

    Devolve `(autorizado, quem_autorizou, como)`. Os dois ultimos alimentam
    o pedido e a auditoria: sem eles, o registro dizia apenas que o operador
    cancelou, e a pergunta "quem liberou?" ficava sem resposta.
    """


    cash_password = str(request.data.get("cash_password") or "")
    if cash_password:
        # SEM SENHA GRAVADA NÃO EXISTE SENHA CERTA.
        #
        # Aqui havia um `else cash_password == "12345678"`: com o campo vazio,
        # essa string fixa cancelava qualquer pedido. E vazio é o estado NORMAL
        # da loja — a senha é excluída da sincronização, então toda instalação
        # local nascia assim. A credencial embutida valia exatamente onde a de
        # verdade não chegava, no lado que fica sem supervisão quando a
        # internet cai.
        #
        # É o mesmo que o movimento de caixa já fazia (`payments/services.py`):
        # sem senha gravada, recusa. Quem precisa cancelar continua tendo a
        # autorização por LOGIN de gerente, logo abaixo — nominal e auditável.
        stored = restaurant.cash_action_password or ""
        approved = bool(stored) and check_password(cash_password, stored)
        # A senha e do restaurante, nao de uma pessoa: quem autorizou e a
        # propria operacao da loja.
        return approved, None, Order.AUTHORIZATION_CASH_PASSWORD

    login = str(request.data.get("authorization_username") or "").strip()
    password = str(request.data.get("authorization_password") or "")
    if not login or not password:
        return False, None, ""

    username = login
    if "@" in login:
        matched = (
            User.objects.filter(
                email__iexact=login,
                profile__account_id=account_id,
            )
            .only("username")
            .first()
        )
        if matched is not None:
            username = matched.get_username()
    authorizer = authenticate(request=request, username=username, password=password)
    if authorizer is None:
        return False, None, ""
    profile = getattr(authorizer, "profile", None)
    if not profile or not profile.is_active or profile.account_id != account_id:
        return False, None, ""
    codes = effective_permission_codes(authorizer)
    approved = is_tenant_admin(authorizer) or "*" in codes or "orders.cancel" in codes
    return approved, (authorizer if approved else None), Order.AUTHORIZATION_DELEGATED


class OrderFilterSet(django_filters.FilterSet):
    # Intervalo de datas por "aberto em" — comparação por data, inclusiva nas duas pontas.
    opened_after = django_filters.DateFilter(field_name="opened_at", lookup_expr="date__gte")
    opened_before = django_filters.DateFilter(field_name="opened_at", lookup_expr="date__lte")
    payment_pending = django_filters.BooleanFilter(method="filter_payment_pending")

    def filter_payment_pending(self, queryset, name, value):
        if value is True:
            return queryset.filter(
                payment_status__in=[Order.PAYMENT_PENDING, Order.PAYMENT_PARTIAL],
                status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
            )
        return queryset

    class Meta:
        model = Order
        # restaurant/branch NÃO entram aqui: o escopo por tenant já os resolve
        # (TenantQuerySetMixin). Declará-los como filtro faz o django-filter validar
        # o UUID fora do contexto de tenant e devolver 400 "Faça uma escolha válida".
        fields = ["order_type", "status", "production_status", "payment_status", "table", "customer"]


class OrderViewSet(BaseTenantViewSet):
    serializer_class = OrderSerializer
    queryset = (
        # Só a comanda vai no JOIN (a busca pelo número dela já junta a
        # tabela). O resto vem por prefetch: nove tabelas largas num JOIN
        # custavam ~60 ms só de PLANEJAMENTO no Postgres, a cada listagem.
        Order.objects.select_related("command")
        .prefetch_related(
            "restaurant", "branch", "table", "customer", "delivery_address", "invoice",
            # `operator_label` lê o usuário responsável.
            "responsible_user",
            "items__product",
            # `restaurant_name` do item.
            "items__restaurant",
            "items__addons",
            "items__batch",
            # `command_label` lê a comanda de cada item.
            "items__command",
            # `payments` entrou no serializer; sem o prefetch a listagem faria
            # uma consulta por pedido.
            "payments__payment_method",
        )
        .all()
    )
    filterset_class = OrderFilterSet
    search_fields = [
        "sequence_text",
        "customer__name",
        "table__number",
        "command__code",
        "command_number_text",
    ]
    ordering_fields = ["updated_at", "opened_at", "closed_at", "total", "sequence"]
    ordering = ["-updated_at"]

    def get_queryset(self):
        # A anotacao precisa ser aplicada aqui, e nao no `queryset` da classe:
        # o mixin de tenant remonta a consulta a partir do model e descartaria
        # qualquer annotate declarado la em cima.
        return (
            super()
            .get_queryset()
            .annotate(
                sequence_text=Cast("sequence", CharField()),
                command_number_text=Cast("command__number", CharField()),
            )
        )

    def perform_update(self, serializer):
        """Mexer no dinheiro pela API genérica também refaz taxa e total.

        `discount` e `delivery_fee` são graváveis por `PATCH /orders/{id}/`, e
        ali não passa nenhum serviço: sem este gancho o desconto entrava e o
        `total` continuava o antigo — a mesma classe de divergência que
        derrubava o fechamento do PDV, só por outra porta.
        """
        money_inputs = {"discount", "delivery_fee"}
        touched = money_inputs & set(serializer.validated_data)
        super().perform_update(serializer)
        if touched:
            recalculate_order(serializer.instance)
            serializer.instance.refresh_from_db()

    @action(detail=True, methods=["post"], url_path="attach-commands")
    def attach_commands(self, request, pk=None):
        """Inclui o consumo de uma ou mais comandas neste pedido.

        Substitui a antiga conta agrupada. Antes, pagar quatro cartões juntos
        exigia quatro PEDIDOS e uma consolidação que movia item por item entre
        eles — o caminho que não aguentava uma mesa grande. Agora a comanda não
        tem pedido: ela anota, e o pedido do caixa recebe as anotações
        pendentes.
        """
        from apps.synchronization.services import loja_no_ar

        order = self.get_object()
        if loja_no_ar.recusar_fechamento(request, order.restaurant):
            # Fechar comanda na nuvem com a loja no ar cobraria o cartão duas
            # vezes (ver `loja_no_ar.py`). O PDV lê o código e volta à loja.
            return Response({"code": loja_no_ar.CODIGO, "message": loja_no_ar.MENSAGEM},
                            status=status.HTTP_409_CONFLICT)
        referencias = request.data.get("commands") or []
        if not isinstance(referencias, list) or not referencias:
            return Response(
                {"detail": "Informe as comandas a incluir nesta conta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            attach_commands_to_order(
                order=order, command_ids=referencias, user=request.user
            )
        except ValidationError as exc:
            # 409, e não 400: o corpo está certo — o que mudou foi o estado do
            # cartão. O PDV trata 400 como erro de preenchimento e reenvia o
            # mesmo corpo para sempre.
            return Response({"detail": exc.messages}, status=status.HTTP_409_CONFLICT)
        order.refresh_from_db()
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"], url_path="detach-commands")
    def detach_commands(self, request, pk=None):
        """Tira comandas desta conta SEM cancelar nada.

        O desfazer do caixa: incluiu o cartão errado, ou o cliente resolveu
        pagar separado. As anotações voltam a pendentes e o cartão volta a ter
        o que cobrar — cancelar a conta inteira para corrigir uma inclusão
        seria caro demais para um engano de um toque.
        """
        from apps.synchronization.services import loja_no_ar

        order = self.get_object()
        if loja_no_ar.recusar_fechamento(request, order.restaurant):
            # Fechar comanda na nuvem com a loja no ar cobraria o cartão duas
            # vezes (ver `loja_no_ar.py`). O PDV lê o código e volta à loja.
            return Response({"code": loja_no_ar.CODIGO, "message": loja_no_ar.MENSAGEM},
                            status=status.HTTP_409_CONFLICT)
        referencias = request.data.get("commands") or []
        if not isinstance(referencias, list) or not referencias:
            return Response(
                {"detail": "Informe as comandas a remover desta conta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            resumo = detach_commands_from_order(
                order=order, command_ids=referencias, user=request.user
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_409_CONFLICT)
        order.refresh_from_db()
        dados = dict(self.get_serializer(order).data)
        # Quem já foi para a produção volta para a comanda com o prato feito —
        # o cozinheiro não desfaz, e o operador precisa saber disso.
        dados["detached"] = resumo
        return Response(dados)

    def _attending_user(self, restaurant):
        """Quem esta atendendo, quando nao e quem gravou.

        O Caixa Principal executa as operacoes do app do garcom com as
        proprias credenciais — e ele quem tem a sessao com a nuvem. Sem esta
        atribuicao o pedido nascia no nome do caixa e a comanda saia na cozinha
        com "ATENDENTE: <caixa>", escondendo quem de fato atendeu a mesa.

        `created_by` continua sendo quem gravou (verdade de auditoria); so o
        atendimento e atribuido, e apenas a um usuario do mesmo restaurante.
        """
        raw = str(self.request.data.get("responsible_user") or "").strip()
        if not raw:
            return None
        try:
            return (
                get_user_model()
                .objects.filter(pk=raw, profile__restaurant=restaurant)
                .first()
            )
        except (ValueError, ValidationError):
            return None

    @action(detail=False, methods=["post"], url_path="create-with-item")
    def create_with_item(self, request):
        """Creates the order and first item in one transaction.

        This is the waiter-app entry point: dismissing a picker never leaves an
        empty counter/delivery/takeaway/command order behind.
        """
        profile = getattr(request.user, "profile", None)
        restaurant = getattr(profile, "restaurant", None)
        if restaurant is None:
            return Response({"detail": "Usuário sem restaurante vinculado."}, status=status.HTTP_400_BAD_REQUEST)

        order_type = request.data.get("order_type")
        if order_type not in {Order.TYPE_COMMAND, Order.TYPE_COUNTER, Order.TYPE_DELIVERY, Order.TYPE_TAKEAWAY}:
            return Response({"order_type": "Tipo de pedido inválido."}, status=status.HTTP_400_BAD_REQUEST)

        command = None
        table = None
        if order_type == Order.TYPE_COMMAND:
            # A COMANDA É OPCIONAL AQUI, e isso não é folga: no modelo de hoje
            # a comanda ANOTA, ela não abre o pedido. Uma conta pode cobrar
            # duzentos cartões, que entram depois por `attach-commands` — não
            # existe "a" comanda deste pedido para mandar no corpo.
            #
            # Exigir o campo quebrava o caso central do caixa: a mesa chega com
            # dois cartões anexados, o cliente pede mais uma cerveja, e passar
            # esse item respondia "Selecione uma comanda válida" — sobre uma
            # conta que já tinha duas.
            #
            # O tipo segue `command` de propósito: é o que o relatório agrupa,
            # e trocá-lo por `counter` porque o corpo veio sem id faria a mesma
            # venda cair em duas colunas conforme a ordem dos toques.
            referencia = request.data.get("command")
            if referencia:
                command = Command.objects.filter(
                    pk=referencia,
                    restaurant=restaurant,
                    is_active=True,
                ).first()
                # Informada e não encontrada continua sendo recusa: o app do
                # garçom manda o cartão que ele leu, e aceitar em silêncio um
                # id inválido lançaria o item num cartão que ninguém escolheu.
                if command is None:
                    return Response({"command": "Selecione uma comanda válida."}, status=status.HTTP_400_BAD_REQUEST)
            if request.data.get("table"):
                from apps.restaurants.models import Table

                table = Table.objects.filter(
                    pk=request.data["table"],
                    restaurant=restaurant,
                    is_active=True,
                ).first()
                if table is None:
                    return Response({"table": "Selecione uma mesa válida."}, status=status.HTTP_400_BAD_REQUEST)

        raw_item = request.data.get("item")
        if not isinstance(raw_item, dict) or not raw_item.get("product"):
            return Response({"item": "Adicione o primeiro item do pedido."}, status=status.HTTP_400_BAD_REQUEST)
        product = Product.objects.filter(pk=raw_item["product"], restaurants=restaurant, is_active=True).first()
        if product is None:
            return Response({"item": "O produto selecionado não está disponível."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item_data = build_first_item_data(
                raw_item=raw_item,
                request_data=request.data,
                account=restaurant.account,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        # A comanda ja tem pedido aberto: o item entra NELE.
        #
        # Recusar com 409 so fazia sentido quando quem chamava estava on-line e
        # podia reabrir o pedido na tela. O app do garcom lanca offline: quando
        # a operacao enfileirada finalmente sobe, a comanda quase sempre ja foi
        # aberta por alguem (o proprio garcom em outro aparelho, o caixa, ou a
        # mesma operacao vinda por outro caminho). O 409 transformava isso em
        # pendencia bloqueada e o item simplesmente sumia do pedido.
        #
        # `add_order_item` continua recusando um pedido pago, cancelado ou
        # estornado, que e o unico caso em que "reabra o pedido" e a resposta
        # certa.
        existing_order = None
        if command is not None and command.current_order_id:
            existing_order = Order.objects.filter(
                pk=command.current_order_id,
                restaurant=restaurant,
            ).first()
        if existing_order is not None:
            try:
                item = add_order_item(order=existing_order, product=product, user=request.user, **item_data)
            except ValidationError as exc:
                return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
            existing_order = Order.objects.prefetch_related(
                "items__product", "items__addons", "items__batch"
            ).get(pk=existing_order.pk)
            return Response(
                self._with_created_item(self.get_serializer(existing_order).data, item, raw_item),
                status=status.HTTP_200_OK,
            )

        try:
            order = create_order_with_item(
                restaurant=restaurant,
                order_type=order_type,
                command=command,
                table=table,
                product=product,
                user=request.user,
                item_data=item_data,
                responsible_user=self._attending_user(restaurant),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            self._with_created_item(self.get_serializer(order).data, order.items.first(), raw_item),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _with_created_item(data, item, raw_item):
        """Diz ao cliente QUAL item desta resposta e o que ele acabou de lancar.

        A resposta e o pedido inteiro, e o item pode ter entrado numa linha que
        ja existia (itens pendentes iguais se agrupam) ou num pedido que outro
        terminal abriu antes. O PDV lancou o item offline com um id temporario
        (`client_item_id`) e precisa troca-lo pelo real: sem saber qual e, a
        copia local ficava com os dois e o item aparecia duas vezes na comanda.
        """
        data["created_item_id"] = str(item.pk) if item is not None else None
        data["client_item_id"] = raw_item.get("client_item_id")
        return data

    def perform_create(self, serializer):
        user = self.request.user
        profile = getattr(user, "profile", None)
        restaurant = serializer.validated_data.get("restaurant") or profile.restaurant
        branch = None
        order = create_order(
            restaurant=restaurant,
            branch=branch,
            order_type=serializer.validated_data["order_type"],
            user=user,
            responsible_user=self._attending_user(restaurant),
            table=serializer.validated_data.get("table"),
            command=serializer.validated_data.get("command"),
            customer=serializer.validated_data.get("customer"),
            delivery_address=serializer.validated_data.get("delivery_address"),
            delivery_fee=serializer.validated_data.get("delivery_fee", 0),
            general_notes=serializer.validated_data.get("general_notes", ""),
            # Quem abre a conta por aqui tambem informa o codigo. `create_order`
            # e o unico lugar que cobra a exigencia do restaurante: deixar o CRUD
            # de fora abriria a porta que a configuracao acabou de fechar.
            metafields=serializer.validated_data.get("metafields"),
        )
        serializer.instance = order

    @action(detail=True, methods=["get", "post"], url_path="items")
    def items(self, request, pk=None):
        order = self.get_object()
        if request.method == "GET":
            serializer = OrderItemSerializer(order.items.all(), many=True)
            return Response(serializer.data)


        # Ler o corpo com `[]` e resolver o produto com `.get()` transformava
        # dois erros de CLIENTE em 500: item sem `product` virava `KeyError`, e
        # produto inexistente (ou de outro restaurante) virava `DoesNotExist`.
        # Os dois são 400 — o operador precisa da mensagem, não de "erro
        # interno". O app do garçom e a fila offline do PDV chegam aqui com
        # payload montado em outro aparelho: assumir que o campo veio é o mesmo
        # que confiar no cliente.
        product_id = request.data.get("product")
        if not product_id:
            return Response(
                {"detail": "Informe o produto do item."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            product = Product.objects.filter(
                Q(restaurants=order.restaurant),
                pk=product_id,
            ).first()
        except (ValueError, ValidationError):
            # `pk` que nem é UUID: o filtro estoura antes de consultar.
            product = None
        if product is None:
            return Response(
                {"detail": "O produto informado não existe ou não pertence a este restaurante."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        scale_reading = None
        if request.data.get("scale_reading"):
            try:
                scale_reading = ScaleReading.objects.select_related("scale").get(
                    pk=request.data["scale_reading"],
                    account=order.account,
                )
            except ScaleReading.DoesNotExist:
                return Response({"detail": "Leitura de balanca nao encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            item = add_order_item(
                order=order,
                product=product,
                quantity=request.data.get("quantity"),
                user=request.user,
                variations=request.data.get("variations", []),
                addons=request.data.get("addons", []),
                customer_note=request.data.get("customer_note", ""),
                scale_reading=scale_reading,
                weight_kg=request.data.get("weight_kg"),
                expected_unit_price=request.data.get("expected_unit_price"),
                metafields=request.data.get("metafields"),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"items/(?P<item_pk>[^/.]+)/quantity")
    def set_item_quantity(self, request, pk=None, item_pk=None):
        """Ajusta a quantidade de um item pendente (teclas + e - do PDV)."""
        try:
            item = OrderItem.objects.get(pk=item_pk, order=self.get_object())
            item = set_order_item_quantity(item, request.user, request.data.get("quantity"))
        except OrderItem.DoesNotExist:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except (ValidationError, InvalidOperation, TypeError):
            return Response(
                {"detail": "Informe uma quantidade válida maior que zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(OrderItemSerializer(item).data)

    @action(detail=True, methods=["delete"], url_path=r"items/(?P<item_pk>[^/.]+)/void")
    def void_item(self, request, pk=None, item_pk=None):
        """Cancela um item do pedido.

        Duas regras podem barrar depois que o prato chegou à produção: a janela
        de tempo do restaurante e a coluna do KDS em que o item está. As duas
        são liberáveis por quem responde — a senha de operação ou a credencial
        de um usuário com permissão, no mesmo corpo do pedido de cancelamento.
        """
        order = self.get_object()
        authorized, authorizer, _how = _can_authorize_cancellation(
            request, order.restaurant, order.account_id
        )
        try:
            item = OrderItem.objects.get(pk=item_pk, order=order)
            item = void_order_item(
                item,
                request.user,
                reason=request.data.get("reason", ""),
                offline_printed=bool(request.data.get("offline_printed")),
                authorized=authorized,
                authorized_by=authorizer,
            )
        except OrderItem.DoesNotExist:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except CancelamentoBloqueado as exc:
            # 409 com código próprio: o terminal reconhece e oferece a
            # autorização do supervisor. Ver `CancelBlocked`.
            raise CancelBlocked(" ".join(exc.messages)) from exc
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderItemSerializer(item).data)

    @action(detail=True, methods=["post"], url_path=r"items/(?P<item_pk>[^/.]+)/comp")
    def comp_item(self, request, pk=None, item_pk=None):
        """Comp an in-production item (courtesy after sending to kitchen)."""
        try:
            item = OrderItem.objects.get(pk=item_pk, order=self.get_object())
            item = comp_order_item(item, request.user, reason=request.data.get("reason", ""))
        except OrderItem.DoesNotExist:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderItemSerializer(item).data)

    @action(detail=True, methods=["get"], url_path="batches")
    def batches(self, request, pk=None):
        """List all production rounds for an order."""
        order = self.get_object()
        batches = OrderBatch.objects.filter(order=order).prefetch_related("items__product")
        serializer = OrderBatchSerializer(batches, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="send-to-kitchen")
    def send_to_kitchen(self, request, pk=None):
        order = self.get_object()
        # Nada pendente: a rodada que esta chamada queria enviar ja foi.
        #
        # Numa fila de entrega ao-menos-uma-vez isso e sucesso, nao erro. O app
        # do garcom enfileira o envio, e quando a operacao sobe os itens quase
        # sempre ja foram enviados — pela repeticao da propria operacao, pelo
        # caixa, ou por outro aparelho. Respondendo 400, a operacao virava
        # pendencia bloqueada e a comanda ficava presa em "aguardando" ate
        # alguem remover a pendencia na mao. Quem chama pela tela nunca cai
        # aqui: o botao de enviar so existe com item pendente.
        if not order.is_locked and not order.items.filter(status=OrderItem.STATUS_PENDING).exists():
            return Response(self.get_serializer(order).data)
        try:
            order = send_order_to_kitchen(
                order,
                request.user,
                client_batch_serial=request.data.get("client_batch_serial"),
                offline_printed=bool(request.data.get("offline_printed")),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"], url_path="checkout")
    def checkout(self, request, pk=None):
        """Grava as escolhas da tela de pagamento sem avançar o pedido.

        Mesmo corpo do `/close/`; o pedido continua ABERTO até o primeiro
        recebimento. Ver `close_order(marcar_aguardando=False)`.
        """
        return self.close(request, pk=pk, marcar_aguardando=False)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None, marcar_aguardando=True):
        order_to_close = self.get_object()
        try:
            order = close_order(
                order_to_close,
                request.user,
                marcar_aguardando=marcar_aguardando,
                discount=request.data.get("discount", 0),
                service_fee=request.data.get("service_fee"),
                service_fee_enabled=request.data.get("service_fee_enabled"),
                fiscal_customer_cpf=request.data.get("fiscal_customer_cpf"),
                fiscal_customer_cnpj=request.data.get("fiscal_customer_cnpj"),
                expected_total=request.data.get("expected_total"),
                # `None` quando a chave nao vem: fechar de novo para corrigir a
                # taxa nao pode derrubar o cupom que ja estava aplicado.
                coupon_code=request.data.get("coupon_code"),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        data = dict(self.get_serializer(order).data)
        reconciled = bool(getattr(order, "_total_reconciled", False))
        data["total_reconciled"] = reconciled
        if reconciled:
            data["client_expected_total"] = str(order._client_expected_total)
            data["authoritative_total"] = data["total"]
        return Response(data)

    @action(detail=True, methods=["post"], url_path="apply-coupon")
    def apply_coupon(self, request, pk=None):
        """Aplica, troca ou retira o cupom do pedido. `code` vazio RETIRA.

        Serve o pedido ABERTO e o pedido em PAGAMENTO, e os dois de propósito: o
        cliente informa o cupom antes de fechar, e informa também no meio do
        pagamento, quando lembra. Obrigar a fechar para descobrir se o cupom
        vale faria o caixa fechar e reabrir a conta na frente dele; e obrigar a
        voltar para o pedido faria ele desfazer o fechamento por causa de um
        código.

        Quem decide se pode é `promotions.coupon_service`: venda já paga,
        cancelada ou bloqueada recusa, e o total nunca pode cair abaixo do que já
        foi recebido.
        """
        from apps.promotions.coupon_service import mexer_no_cupom

        codigo = request.data.get("code")
        if codigo is None:
            # `None` aqui seria "não mexe", e não existe "não mexe" numa rota
            # cujo único propósito é mexer: o cliente mandou a requisição errada.
            return Response(
                {"detail": 'Informe "code" com o cupom, ou vazio para retirar.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = mexer_no_cupom(self.get_object(), codigo)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        from apps.payments.serializers import PaymentSerializer
        from apps.payments.services import register_payment
        from apps.payments.terminals import (
            CashSessionConflict,
            CashSessionForbidden,
            installation_id_from_request,
            terminal_from_request,
        )
        from apps.payments.views import cash_session_error_response

        order = self.get_object()
        payment_metadata = request.data.get("metadata", {})
        payment_metadata = dict(payment_metadata) if isinstance(payment_metadata, dict) else {}
        if request.data.get("card_subtype"):
            payment_metadata["card_subtype"] = request.data["card_subtype"]
        # Recebimento sem forma ou sem valor é erro de preenchimento, não falha
        # do servidor. Lidos com `[]`, os dois viravam `KeyError` e 500 — e o
        # PDV tratava 500 como falha temporária, devolvendo a operação à fila
        # para tentar de novo para sempre em vez de mandá-la para revisão.
        if not request.data.get("payment_method"):
            return Response(
                {"detail": "Selecione a forma de pagamento."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if request.data.get("amount") in (None, ""):
            return Response(
                {"detail": "Informe o valor recebido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payment = register_payment(
                order=order,
                user=request.user,
                payment_method_id=request.data["payment_method"],
                amount=request.data["amount"],
                # A chave do CORPO primeiro: o PDV a gera quando o recebimento
                # entra na tela e a repete em toda tentativa. A do cabeçalho
                # muda a cada chamada, e com ela a repetição do operador depois
                # de uma falha de rede virava um segundo pagamento.
                idempotency_key=request.data.get("idempotency_key") or request.headers.get("Idempotency-Key"),
                metadata=payment_metadata,
                cash_register_id=request.data.get("cash_register"),
                # O dinheiro entra na gaveta de UM terminal: o recebimento
                # segue a mesma regra de dono da sangria e do fechamento.
                terminal=terminal_from_request(request, restaurant=order.restaurant),
                installation_id=installation_id_from_request(request),
            )
        except (CashSessionConflict, CashSessionForbidden) as exc:
            return cash_session_error_response(exc)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="payments")
    def payments(self, request, pk=None):
        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer

        order = self.get_object()
        payments = Payment.objects.filter(order=order, status=Payment.STATUS_APPROVED).order_by("created_at")
        return Response(PaymentSerializer(payments, many=True).data)

    @action(detail=True, methods=["delete"], url_path=r"payments/(?P<payment_pk>[^/.]+)")
    def delete_payment(self, request, pk=None, payment_pk=None):
        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer
        from apps.payments.services import cancel_payment

        payment = Payment.objects.filter(
            pk=payment_pk,
            order=self.get_object(),
            status=Payment.STATUS_APPROVED,
        ).first()
        if payment is None:
            return Response({"detail": "Pagamento não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        try:
            payment = cancel_payment(payment=payment, user=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentSerializer(payment).data)

    def perform_destroy(self, instance):
        # Pedido com nota ou pagamento é VENDA: cancela-se, não se apaga
        # (ver `bulk_delete.py`). Antes a exclusão individual não tinha trava.
        from rest_framework.exceptions import APIException

        from django.db import transaction

        from apps.orders.bulk_delete import motivo_para_manter, travar_para_excluir

        with transaction.atomic():
            instance = travar_para_excluir(instance)
            motivo = motivo_para_manter(instance)
            if motivo:
                erro = APIException(f"Pedido #{instance.sequence} {motivo}.")
                erro.status_code = status.HTTP_409_CONFLICT
                raise erro
            super().perform_destroy(instance)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Exclui vários pedidos sem rastro fiscal/financeiro — ver `bulk_delete.py`."""
        from apps.orders.bulk_delete import MAXIMO, excluir_em_massa

        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids or len(ids) > MAXIMO:
            return Response({"detail": f"Selecione de 1 a {MAXIMO} pedidos."}, status=status.HTTP_400_BAD_REQUEST)
        pedidos = list(self.get_queryset().filter(pk__in=ids))
        return Response(excluir_em_massa(pedidos, user=request.user))

    @action(detail=False, methods=["post"], url_path="bulk-cancel")
    def bulk_cancel(self, request):
        """Cancela vários pedidos (e as notas deles) — ver `bulk_cancel.py`."""
        from apps.orders.bulk_cancel import MAXIMO, cancelar_em_massa

        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids or len(ids) > MAXIMO:
            return Response({"detail": f"Selecione de 1 a {MAXIMO} pedidos."}, status=status.HTTP_400_BAD_REQUEST)
        por_restaurante = {}  # a senha é conferida uma vez por unidade, não por pedido

        def autorizar(pedido):
            if pedido.restaurant_id not in por_restaurante:
                por_restaurante[pedido.restaurant_id] = _can_authorize_cancellation(
                    request, pedido.restaurant, pedido.account_id
                )
            return por_restaurante[pedido.restaurant_id]

        try:
            resultado = cancelar_em_massa(
                list(self.get_queryset().filter(pk__in=ids)), user=request.user,
                reason=request.data.get("reason", ""), autorizar=autorizar,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resultado)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        from apps.orders.services import order_is_empty

        order = self.get_object()
        # DESCARTAR UM PEDIDO VAZIO NAO E CANCELAR UMA VENDA.
        #
        # Sem item e sem recebimento nao ha nada para proteger: a autorizacao
        # do supervisor existe para impedir que alguem apague consumo ja
        # lancado. Exigi-la aqui deixava a comanda ocupada por um pedido que
        # nunca virou nada — e travava o proximo cliente que fosse usa-la.
        from apps.orders.services import order_within_cancellation_grace

        # A carência é uma regra DO PEDIDO: dentro dela nada chegou à produção,
        # então não há consumo a proteger e a senha só atrasaria quem digitou
        # errado. Fica aqui, e não no validador, porque o cancelamento de ITEM
        # tem as regras dele.
        if order_within_cancellation_grace(order):
            authorized, authorizer, authorization = True, None, Order.AUTHORIZATION_GRACE
        else:
            authorized, authorizer, authorization = _can_authorize_cancellation(
                request, order.restaurant, order.account_id
            )
        if not order_is_empty(order) and not authorized:
            return Response(
                {
                    "detail": (
                        "Informe a senha de operação do restaurante ou as "
                        "credenciais de um usuário com permissão para cancelar pedidos."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        vazio = order_is_empty(order)
        try:
            order = cancel_order(
                order,
                request.user,
                request.data.get("reason", ""),
                authorized_by=authorizer,
                # Pedido vazio descartado nao passou por autorizacao nenhuma.
                authorization=authorization or Order.AUTHORIZATION_OWN,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        data = dict(self.get_serializer(order).data)
        # O comprovante sai para QUEM cancelou; pedido vazio nunca.
        if order.restaurant.print_cancellation_receipt and not vazio:
            from apps.printers.cancellation_receipt import cancellation_print_response

            data.update(cancellation_print_response(
                order=order, user=request.user,
                terminal_prints=bool(request.data.get("print_on_terminal")),
            ))
        return Response(data)


    @action(detail=True, methods=["post"], url_path="print")
    def print_order(self, request, pk=None):
        from apps.printers.models import Printer
        from apps.printers.services import printer_payload, register_print_job

        order = self.get_object()
        printer = None
        printer_id = request.data.get("printer")
        if printer_id:
            printer = Printer.objects.filter(
                pk=printer_id,
                account=order.account,
                restaurant=order.restaurant,
                is_active=True,
            ).first()
            if printer is None:
                return Response(
                    {"detail": "A impressora selecionada não existe, está inativa ou pertence a outro restaurante."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            job = register_print_job(
                order=order,
                user=request.user,
                job_type=request.data.get("job_type", "receipt"),
                printer=printer,
                manual_only=bool(request.data.get("manual_only", False)),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        printer = job.printer
        return Response(
            {
                "print_job_id": str(job.id),
                "html": job.html_content,
                # O agente local usa payload.text_content (e barcode/QR) como
                # texto pronto pro cupom termico; sem isso ele caia pro
                # conversor generico de HTML, que nao entende tabela e gruda
                # rotulo com valor ("SubtotalR$ 237,00").
                "payload": job.payload,
                "status": job.status,
                "printer": printer_payload(job.printer),
            }
        )


class OrderItemViewSet(BaseTenantViewSet):
    serializer_class = OrderItemSerializer
    queryset = (
        OrderItem.objects.select_related("restaurant", "branch", "order__table", "order__command", "product", "batch")
        .prefetch_related("addons")
        .all()
    )
    filterset_fields = ["order", "production_sector", "status"]
    search_fields = ["product__name", "customer_note"]
    ordering_fields = ["launched_at", "ready_at"]

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
