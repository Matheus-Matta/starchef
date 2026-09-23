from datetime import timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.template.loader import get_template
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.numbers import MAX_WEIGHT, parse_decimal
from apps.core.viewsets import BaseTenantViewSet
from apps.core.permissions import CanOperateScale, CanUseOrManageDevices
from apps.orders.serializers import OrderItemSerializer
from apps.printers.models import Printer, PrintJob, Scale, ScaleReading
from apps.printers.serializers import (
    PrinterSerializer,
    PrintJobSerializer,
    ScaleReadingSerializer,
    ScaleSerializer,
)
from apps.printers.services import weigh_to_order


class DevicePollingRateThrottle(UserRateThrottle):
    scope = "device_poll"


class PrinterViewSet(BaseTenantViewSet):
    permission_classes = [CanUseOrManageDevices]
    serializer_class = PrinterSerializer
    queryset = Printer.objects.select_related("restaurant", "branch", "sector").all()
    filterset_fields = ["restaurant", "driver_type", "sector", "is_active"]
    search_fields = ["name", "endpoint"]

    @action(detail=False, methods=["get"], url_path="templates")
    def templates(self, request):
        """Modelos oficiais baixados e armazenados pelo agente desktop."""
        definitions = {
            "receipt": ("printers/receipt.html", ["receipt", "table_bill", "cash_close"]),
            "kitchen_ticket": ("printers/kitchen_ticket.html", ["kitchen_ticket", "bar_ticket"]),
            "weigh_ticket": ("printers/weigh_ticket.html", ["weigh_ticket"]),
            "danfe_nfce": ("printers/danfe_nfce.html", ["fiscal_danfe"]),
        }
        templates = []
        for key, (template_name, job_types) in definitions.items():
            source = get_template(template_name).template.source
            templates.append(
                {
                    "key": key,
                    "template_name": template_name,
                    "job_types": job_types,
                    "version": sha256(source.encode("utf-8")).hexdigest(),
                    "content": source,
                }
            )
        return Response({"templates": templates})

    @action(detail=True, methods=["post"], url_path="test-connection")
    def test_connection(self, request, pk=None):
        """Cria uma nota diagnóstica para impressão manual no PDV Desktop."""
        from apps.printers.services import register_printer_test_job

        printer = self.get_object()
        job = register_printer_test_job(printer=printer, user=request.user)
        return Response(
            {
                "print_job_id": str(job.id),
                "status": job.status,
                "html": job.html_content,
                "payload": job.payload,
                "printer": {
                    "id": str(printer.id),
                    "name": printer.name,
                    "endpoint": printer.endpoint,
                    "connection_type": printer.connection_type,
                    "host": printer.host,
                    "port": printer.port,
                    "timeout_seconds": printer.timeout_seconds,
                    "driver_type": printer.driver_type,
                    "settings": printer.settings,
                    "auto_print": printer.auto_print,
                    "is_active": printer.is_active,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class ScaleViewSet(BaseTenantViewSet):
    permission_classes = [CanUseOrManageDevices]
    serializer_class = ScaleSerializer
    queryset = Scale.objects.select_related("restaurant", "branch", "sector").all()
    filterset_fields = ["restaurant", "protocol", "is_active"]
    search_fields = ["name", "port"]

    def get_permissions(self):
        if self.action in {"checkout_command", "bind_command", "release_command"}:
            return [CanOperateScale()]
        if self.action in {"claim_agent", "release_agent"}:
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_throttles(self):
        if self.action in {"latest_reading", "claim_agent", "release_agent"}:
            return [DevicePollingRateThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=["post"], url_path="bind-command")
    def bind_command(self, request, pk=None):
        """O cliente passou o cartão: amarra a comanda por um tempo curto.

        O vínculo expira na primeira pesagem e também por tempo, o que vier
        antes — sem isso, o prato do próximo cliente cai na comanda do
        anterior, que é o defeito de dinheiro deste desenho.
        """
        from apps.printers.scale_command import bind_command_to_scale

        try:
            scale = bind_command_to_scale(
                scale=self.get_object(),
                reference=request.data.get("command") or request.data.get("code"),
                user=request.user,
            )
        except ValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(scale).data)

    @action(detail=True, methods=["post"], url_path="release-command")
    def release_command(self, request, pk=None):
        """Solta o cartão sem pesar (o cliente desistiu, leu o cartão errado)."""
        from apps.printers.scale_command import release_command_binding

        with transaction.atomic():
            scale = Scale.objects.select_for_update().get(pk=self.get_object().pk)
            release_command_binding(scale)
        return Response(self.get_serializer(scale).data)

    @action(detail=True, methods=["post"], url_path="claim-agent")
    def claim_agent(self, request, pk=None):
        """Concede uma posse curta e exclusiva da leitura a um PDV Desktop."""
        instance_id = str(request.data.get("instance_id", "")).strip()[:120]
        if not instance_id:
            return Response(
                {"detail": "Identificador do PDV não informado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        now = timezone.now()
        lease_seconds = 15
        with transaction.atomic():
            scale = Scale.objects.select_for_update().get(pk=self.get_object().pk)
            owned_by_other = (
                scale.agent_instance_id
                and scale.agent_instance_id != instance_id
                and scale.agent_lease_expires_at
                and scale.agent_lease_expires_at > now
            )
            if owned_by_other:
                return Response(
                    {
                        "claimed": False,
                        "detail": "Esta balança está sendo monitorada por outro PDV.",
                        "lease_expires_at": scale.agent_lease_expires_at,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            scale.agent_instance_id = instance_id
            scale.agent_lease_expires_at = now + timedelta(seconds=lease_seconds)
            scale.updated_by = request.user
            scale.save(
                update_fields=[
                    "agent_instance_id",
                    "agent_lease_expires_at",
                    "updated_by",
                    "updated_at",
                ]
            )
        return Response(
            {
                "claimed": True,
                "lease_seconds": lease_seconds,
                "lease_expires_at": scale.agent_lease_expires_at,
            }
        )

    @action(detail=True, methods=["post"], url_path="release-agent")
    def release_agent(self, request, pk=None):
        instance_id = str(request.data.get("instance_id", "")).strip()[:120]
        with transaction.atomic():
            scale = Scale.objects.select_for_update().get(pk=self.get_object().pk)
            if scale.agent_instance_id == instance_id:
                scale.agent_instance_id = ""
                scale.agent_lease_expires_at = None
                scale.updated_by = request.user
                scale.save(
                    update_fields=[
                        "agent_instance_id",
                        "agent_lease_expires_at",
                        "updated_by",
                        "updated_at",
                    ]
                )
        return Response({"released": True})

    @action(detail=True, methods=["get"], url_path="latest-reading")
    def latest_reading(self, request, pk=None):
        """Ultima leitura valida da balanca, respeitando reading_max_age_seconds. Usada pelo PDV."""
        scale = self.get_object()
        cutoff = timezone.now() - timedelta(seconds=scale.reading_max_age_seconds)
        reading = (
            ScaleReading.objects.filter(scale=scale, created_at__gte=cutoff, order_item__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if reading is None:
            return Response(
                {"detail": "Nenhuma leitura recente da balanca. Coloque o prato e aguarde, ou digite o peso."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ScaleReadingSerializer(reading, context={"request": request}).data)

    def _resolve_order(self, scale, order_id):
        """Pedido informado no corpo ou, na ausencia, o pedido vinculado a balanca."""
        from apps.orders.models import Order

        if order_id:
            return Order.objects.filter(pk=order_id, account=scale.account).first()
        return scale.active_order

    @action(detail=True, methods=["post"], url_path="bind-order")
    def bind_order(self, request, pk=None):
        """Vincula (ou desvincula com order=null) um pedido a balanca para o gatilho automatico."""
        scale = self.get_object()
        scale.active_order = self._resolve_order(scale, request.data.get("order"))
        scale.updated_by = request.user
        scale.save(update_fields=["active_order", "updated_by", "updated_at"])
        return Response(ScaleSerializer(scale, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="weigh")
    def weigh(self, request, pk=None):
        """Confirmacao a partir do PDV: pesa -> lanca o item por kg -> gera a nota de pesagem."""
        scale = self.get_object()
        order = self._resolve_order(scale, request.data.get("order"))
        if order is None:
            return Response({"detail": "Informe um pedido ou vincule um pedido a balanca."}, status=status.HTTP_400_BAD_REQUEST)

        reading = None
        if request.data.get("scale_reading"):
            reading = ScaleReading.objects.filter(pk=request.data["scale_reading"], account=scale.account).first()

        try:
            item, job = weigh_to_order(
                scale=scale,
                order=order,
                user=request.user,
                scale_reading=reading,
                weight_kg=request.data.get("weight_kg"),
                do_print=request.data.get("print", True),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "item": OrderItemSerializer(item).data,
                "print_job": PrintJobSerializer(job, context={"request": request}).data if job else None,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="checkout-command")
    def checkout_command(self, request, pk=None):
        """Fecha a pesagem NA COMANDA: o prato e os extras viram anotações pendentes.

        Nenhum pedido nasce aqui. A comanda é um bloco de notas, e o pedido só
        existe no caixa — montado com as anotações PENDENTES dos cartões que
        vão ser pagos juntos (ver `apps.orders.command_items`).

        Esta rota tinha ficado para trás quando a comanda virou bloco de notas:
        ela abria um pedido para o cartão e lançava o prato como `OrderItem`. O
        item até era criado, mas fora do lugar onde a comanda é lida hoje — a
        tela do garçom e o caixa perguntam pelas anotações pendentes do cartão,
        então o prato pesado simplesmente não aparecia na comanda. E o pedido
        aberto ainda prendia o cartão a uma conta que talvez ninguém fosse
        pagar, que é exatamente o que `CommandItem` existe para eliminar.
        """
        from apps.menu.models import Product
        from apps.orders.command_items import launch_item
        from apps.orders.serializers_command_item import CommandItemSerializer
        from apps.printers.scale_command import weigh_into_command
        from apps.printers.services import register_command_weigh_print
        from apps.restaurants.models import Command

        command_code = str(request.data.get("command_code", "")).strip()
        reading_id = request.data.get("scale_reading")
        # Peso bruto e a alternativa para o REPLAY de uma pesagem feita com o
        # PDV offline: nesse momento nao existe `ScaleReading`, porque criar
        # uma exige servidor. O terminal ja converteu a leitura em item na
        # copia local; aqui a leitura e materializada junto, para o historico
        # da balanca continuar completo.
        offline_weight = request.data.get("weight_kg")
        extras = request.data.get("extras") or []
        if not command_code:
            return Response({"detail": "Leia ou informe o codigo da comanda."}, status=status.HTTP_400_BAD_REQUEST)
        if not reading_id and offline_weight in (None, ""):
            return Response({"detail": "A leitura da balanca e obrigatoria."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(extras, list) or len(extras) > 20:
            return Response({"detail": "Informe no maximo 20 produtos adicionais."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                scale = Scale.objects.select_for_update().get(pk=self.get_object().pk)
                command_lookup = Q(code=command_code)
                if command_code.isdigit():
                    command_lookup |= Q(number=int(command_code))
                command = (
                    Command.objects.select_for_update()
                    .select_related("restaurant")
                    .filter(
                        command_lookup,
                        account=scale.account,
                        restaurant=scale.restaurant,
                        is_active=True,
                    )
                    .first()
                )
                if command is None:
                    raise ValidationError("Comanda nao encontrada para o restaurante selecionado.")

                if reading_id:
                    reading = (
                        ScaleReading.objects.select_for_update()
                        .filter(
                            pk=reading_id,
                            account=scale.account,
                            scale=scale,
                            is_stable=True,
                            order_item__isnull=True,
                            # A leitura consumida agora vira ANOTACAO, e nao
                            # item de pedido. Sem esta condicao, a mesma
                            # pesagem podia ser lancada de novo na comanda: o
                            # cliente pagaria duas vezes pelo mesmo prato.
                            command_item__isnull=True,
                        )
                        .first()
                    )
                    if reading is None:
                        raise ValidationError("Leitura invalida, instavel ou ja utilizada.")
                else:
                    try:
                        peso = Decimal(str(offline_weight))
                    except (InvalidOperation, TypeError) as exc:
                        raise ValidationError("Peso informado invalido.") from exc
                    if peso <= 0:
                        raise ValidationError("O peso precisa ser maior que zero.")
                    reading = ScaleReading.objects.create(
                        account=scale.account,
                        restaurant=scale.restaurant,
                        branch=scale.branch,
                        scale=scale,
                        weight_kg=peso,
                        # A tara vem do corpo junto do peso; ela escapava da
                        # checagem acima e estourava `InvalidOperation` com
                        # texto no campo — 500 no meio de uma pesagem.
                        tare_kg=parse_decimal(
                            request.data.get("tare_kg"),
                            field="tare_kg",
                            default=0,
                            minimum=Decimal("0"),
                            maximum=MAX_WEIGHT,
                        ),
                        is_stable=True,
                        source="agent",
                        created_by=request.user,
                        updated_by=request.user,
                    )

                weighed_item = weigh_into_command(
                    scale=scale,
                    command=command,
                    user=request.user,
                    scale_reading=reading,
                    # A etiqueta sai uma vez so, depois dos extras.
                    do_print=False,
                )

                extra_items = []
                for entry in extras:
                    if not isinstance(entry, dict):
                        raise ValidationError("Produto adicional invalido.")
                    try:
                        quantity = int(entry.get("quantity", 1))
                    except (TypeError, ValueError) as exc:
                        raise ValidationError("Quantidade adicional invalida.") from exc
                    if quantity < 1 or quantity > 99:
                        raise ValidationError("A quantidade adicional deve ficar entre 1 e 99.")
                    product = Product.objects.filter(
                        Q(restaurants=scale.restaurant),
                        pk=entry.get("product"),
                        account=scale.account,
                        is_active=True,
                    ).first()
                    if product is None or product.is_weighed:
                        raise ValidationError("Produto adicional inexistente ou vendido por peso.")
                    variations = entry.get("variations") or []
                    if not isinstance(variations, list):
                        raise ValidationError("Variacao do adicional invalida.")
                    addons = entry.get("addons") or []
                    if not isinstance(addons, list):
                        raise ValidationError("Lista de adicionais invalida.")
                    customer_note = str(entry.get("customer_note") or "")
                    # A bebida que o cliente pega na balanca e uma anotacao
                    # como qualquer outra: mesma porta de entrada que o garcom
                    # usa, com variacao, adicional e observacao.
                    extra_items.append(
                        launch_item(
                            command=command,
                            product=product,
                            user=request.user,
                            quantity=quantity,
                            variations=variations,
                            addons=addons,
                            customer_note=customer_note,
                        )
                    )

                # Dentro da transacao de proposito: sem impressora resolvida, a
                # pesagem inteira volta atras em vez de consumir a leitura e
                # deixar o cliente sem a etiqueta que ele leva ao caixa.
                print_job = (
                    register_command_weigh_print(
                        command=command,
                        item=weighed_item,
                        scale=scale,
                        user=request.user,
                        offline_printed=bool(request.data.get("offline_printed")),
                    )
                    if request.data.get("print", True)
                    else None
                )
                # `launch_item` marca o cartao como ocupado; a resposta precisa
                # dizer o estado depois disso, e nao o de antes.
                command.refresh_from_db()
                return Response(
                    {
                        "command": {
                            "id": str(command.id),
                            "number": command.number,
                            "code": command.code,
                            "status": command.status,
                        },
                        "weighed_item": CommandItemSerializer(weighed_item).data,
                        "extra_items": CommandItemSerializer(extra_items, many=True).data,
                        "print_job": (
                            PrintJobSerializer(print_job, context={"request": request}).data
                            if print_job
                            else None
                        ),
                    },
                    status=status.HTTP_201_CREATED,
                )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)


class ScaleReadingViewSet(BaseTenantViewSet):
    """POST usado pelo agente local para enviar leituras da balanca."""

    serializer_class = ScaleReadingSerializer
    queryset = ScaleReading.objects.select_related("restaurant", "branch", "scale").all()
    filterset_fields = ["scale", "source", "is_stable"]
    ordering_fields = ["created_at"]
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        # Leituras herdam restaurante/filial da balanca: o agente so envia scale + peso.
        scale = serializer.validated_data.get("scale")
        if scale is not None:
            serializer.validated_data.setdefault("restaurant", scale.restaurant)
            serializer.validated_data.setdefault("branch", scale.branch)

        # A RECUSA NASCE COM A LINHA, e nao num segundo `save()`.
        #
        # `scale_reading` e append-only na sincronizacao (`immutable=True`): o
        # destino INSERE e nunca atualiza. Um motivo gravado depois viraria um
        # evento de UPDATE que a nuvem descarta — e a leitura ficaria la com o
        # motivo em branco para sempre. Quem fosse investigar "por que o prato
        # deste cliente nao foi cobrado?" nao acharia resposta exatamente onde
        # a pergunta e feita.
        comanda, recusa = self.command_mode_refusal(scale, serializer.validated_data)
        if recusa:
            serializer.validated_data["notes"] = recusa

        super().perform_create(serializer)
        if not recusa:
            self._maybe_auto_weigh(serializer.instance, command=comanda)

    def command_mode_refusal(self, scale, dados):
        """Consome o vinculo do cartao e diz por que a pesagem nao vai cobrar.

        Devolve `(comanda, motivo)`. Roda ANTES do INSERT da leitura de
        proposito — ver `perform_create`.

        No modo balcao devolve `(None, "")`: quem decide ali e
        `_maybe_auto_weigh`, e o caminho nao mudou.
        """
        if scale is None or scale.weighing_mode != Scale.MODE_COMMAND:
            return None, ""
        if not scale.auto_print or not scale.product_id:
            return None, ""
        if not dados.get("is_stable", True):
            return None, ""

        from apps.printers.scale_command import consume_command_binding

        comanda = consume_command_binding(scale)
        if comanda is None:
            # FALHA FECHADO: nada de queda para balcao. Um prato do cliente A
            # nao pode virar conta avulsa silenciosa.
            return None, "Pesagem sem comanda: passe o cartao antes de pesar."
        return comanda, ""

    def _register_weigh_failure(self, reading, motivo):
        """Grava por que a pesagem falhou DEPOIS que a leitura ja existia.

        Sao as falhas que so aparecem ao lancar o item: impressora inativa,
        produto fora do cardapio, comanda em fechamento. A nota vai para a
        leitura (o terminal le a resposta e avisa o operador) e TAMBEM para a
        auditoria — que e append-only e sincroniza, e por isso e a unica copia
        que chega a nuvem. Ver `command_mode_refusal` para o porque.
        """
        reading.notes = motivo[:255]
        reading.save(update_fields=["notes", "updated_at"])
        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=reading,
            actor=self.request.user,
            reason=motivo,
            metadata={"event": "scale_reading_not_charged", "scale": str(reading.scale_id or "")},
        )

    def _maybe_auto_weigh(self, reading, *, command=None):
        """Gatilho automatico da leitura estavel, na ORDEM que importa.

        1. modo comanda com cartao valido -> lanca na comanda (abre o pedido de
           trabalho dela se for a primeira pesagem);
        2. modo comanda SEM cartao valido -> a recusa ja foi gravada no INSERT
           por `command_mode_refusal`, e esta funcao nem e chamada. Nao ha
           queda para balcao: um prato do cliente A virando conta avulsa
           silenciosa e pior que um erro visivel no terminal;
        3. modo balcao -> comportamento de sempre (pedido amarrado, ou pedido
           de balcao automatico).
        """
        scale = reading.scale
        if not scale or not scale.auto_print or not reading.is_stable:
            return
        if not scale.product_id:
            return

        from apps.orders.models import Order
        from apps.orders.services import create_order
        from apps.printers.scale_command import weigh_into_command

        if scale.weighing_mode == Scale.MODE_COMMAND:
            if command is None:
                return
            try:
                # A comanda ANOTA o peso; nenhum pedido é aberto aqui.
                weigh_into_command(
                    scale=scale, command=command, user=self.request.user, scale_reading=reading
                )
            except ValidationError as exc:
                self._register_weigh_failure(reading, " ".join(exc.messages))
            return

        order = None
        auto_created = False
        if scale.active_order_id:
            order = Order.objects.filter(
                pk=scale.active_order_id,
                account=scale.account,
                restaurant=scale.restaurant,
            ).first()
        if order is None or order.is_locked:
            order = create_order(
                restaurant=scale.restaurant,
                branch=None,
                order_type=Order.TYPE_COUNTER,
                user=self.request.user,
                general_notes=f"Pedido criado automaticamente pela balanca {scale.name}.",
            )
            auto_created = True
        try:
            weigh_to_order(scale=scale, order=order, user=self.request.user, scale_reading=reading, do_print=True)
            if auto_created:
                order.status = Order.STATUS_AWAITING_PAYMENT
                order.save(update_fields=["status", "updated_at"])
        except ValidationError:
            if auto_created:
                order.delete()
            # Nunca impede o registro da leitura em si. O agente tentara uma
            # nova leitura depois que o peso voltar a zero.


class PrintJobViewSet(BaseTenantViewSet):
    serializer_class = PrintJobSerializer
    queryset = PrintJob.objects.select_related("restaurant", "branch", "printer", "order", "printed_by").all()
    # `status__in` existe para o agente do PDV pedir `scheduled`, `pending` e
    # `rendered` numa requisicao so, em vez de uma por status. Sao tres
    # chamadas a cada ciclo, em cada terminal de cada loja — e o resultado e
    # sempre a mesma lista concatenada.
    filterset_fields = {
        "restaurant": ["exact"],
        "printer": ["exact"],
        "job_type": ["exact"],
        "status": ["exact", "in"],
    }
    ordering_fields = ["created_at", "printed_at"]

    def list(self, request, *args, **kwargs):
        # Compatibilidade operacional: libera qualquer rodada agendada por uma
        # versao anterior que ainda esteja pendente, mesmo sem Celery.
        from apps.orders.services import dispatch_due_kitchen_batches

        account = getattr(request, "account", None)
        if account is not None:
            dispatch_due_kitchen_batches(account_id=account.id)
        self._release_stale_claims()
        return super().list(request, *args, **kwargs)

    # Uma reserva dura o tempo de mandar bytes para uma impressora. Passado
    # isso, quem reservou nao existe mais: o PDV foi fechado, a maquina
    # reiniciou, o processo morreu. Sem devolver, o cupom fica `claimed` para
    # sempre — invisivel para os outros terminais, que so olham `pending` e
    # `rendered`, e a cozinha nunca recebe a comanda.
    CLAIM_TTL = timedelta(minutes=5)

    def _release_stale_claims(self):
        self.get_queryset().filter(
            status=PrintJob.STATUS_CLAIMED,
            updated_at__lt=timezone.now() - self.CLAIM_TTL,
        ).update(status=PrintJob.STATUS_PENDING, updated_at=timezone.now())

    def get_throttles(self):
        if self.action == "list":
            return [DevicePollingRateThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=["post"], url_path="claim")
    def claim(self, request, pk=None):
        """Reserva este cupom para o terminal que esta chamando.

        A fila de impressao e da UNIDADE, nao do terminal: dois PDVs no mesmo
        restaurante consultam a mesma lista de pendentes, e uma impressora de
        rede e alcancavel dos dois. Entre a consulta de um e a de outro cabe
        folga de sobra para os dois ingerirem o mesmo trabalho — e a comanda
        sair duas vezes na cozinha.

        A reserva e um UPDATE condicional: o banco decide quem chegou primeiro.
        Checar e depois gravar nao resolveria, porque as duas transacoes leem
        "pendente" antes de qualquer uma escrever.

        Chamar de novo para um cupom que JA e deste terminal apenas renova a
        reserva. E o que permite uma impressora sem papel ficar meia hora
        insistindo sem que a reserva expire no meio e outro terminal imprima a
        mesma comanda.

        200 = e seu, pode imprimir. 409 = outro terminal levou.
        """
        terminal = (request.headers.get("X-Terminal-Id") or "").strip()
        job = self.get_object()
        renewable = [PrintJob.STATUS_PENDING, PrintJob.STATUS_RENDERED]
        if terminal and job.status == PrintJob.STATUS_CLAIMED:
            if (job.payload or {}).get("claimed_by_terminal") == terminal:
                renewable.append(PrintJob.STATUS_CLAIMED)

        claimed = (
            self.get_queryset()
            .filter(pk=job.pk, status__in=renewable)
            .update(status=PrintJob.STATUS_CLAIMED, updated_at=timezone.now())
        )
        if not claimed:
            job.refresh_from_db()
            return Response(
                {
                    "detail": "Este cupom ja foi assumido por outro terminal.",
                    "status": job.status,
                },
                status=status.HTTP_409_CONFLICT,
            )
        job.refresh_from_db()
        if terminal and (job.payload or {}).get("claimed_by_terminal") != terminal:
            # E o dono da reserva: sem isto, a renovacao acima nao teria como
            # saber que o cupom ja e deste terminal.
            job.payload = {**(job.payload or {}), "claimed_by_terminal": terminal}
            job.save(update_fields=["payload", "updated_at"])
        return Response(PrintJobSerializer(job, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="release")
    def release(self, request, pk=None):
        """Devolve a reserva: este terminal nao vai conseguir imprimir.

        Sem isto, um cupom reservado por um PDV que fechou logo depois ficaria
        parado para sempre — invisivel para os outros terminais, que so olham
        `pending` e `rendered`.
        """
        updated = (
            self.get_queryset()
            .filter(pk=self.get_object().pk, status=PrintJob.STATUS_CLAIMED)
            .update(status=PrintJob.STATUS_PENDING, updated_at=timezone.now())
        )
        return Response({"released": bool(updated)})

    @action(detail=True, methods=["post"], url_path="mark-printed")
    def mark_printed(self, request, pk=None):
        """Chamada pelo agente local apos imprimir com sucesso."""
        job = self.get_object()
        job.status = PrintJob.STATUS_PRINTED
        job.printed_at = timezone.now()
        job.printed_by = request.user
        job.error_message = ""
        job.save(update_fields=["status", "printed_at", "printed_by", "error_message", "updated_at"])
        return Response(PrintJobSerializer(job, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="mark-failed")
    def mark_failed(self, request, pk=None):
        """Chamada pelo agente quando a impressao falha (registra o erro)."""
        job = self.get_object()
        job.status = PrintJob.STATUS_FAILED
        job.error_message = str(request.data.get("error", ""))[:2000]
        job.save(update_fields=["status", "error_message", "updated_at"])
        return Response(PrintJobSerializer(job, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="requeue")
    def requeue(self, request, pk=None):
        """Reimprime este mesmo trabalho, sem criar outro pedido.

        Reenfileirar preserva o conteudo original — inclusive o layout da nota
        de pesagem e o Code 128 da comanda —, o que gerar um novo trabalho a
        partir do pedido nao faria. Nenhum item e recalculado nem duplicado:
        apenas o estado volta para `rendered` e o agente local imprime de novo.
        """
        with transaction.atomic():
            job = PrintJob.objects.select_for_update().get(pk=self.get_object().pk)
            # O agente local consome `pending` e `rendered`. Reenfileirar um
            # trabalho que ainda esta na fila produziria uma segunda impressao
            # silenciosa, entao so `printed` e `failed` podem ser repetidos.
            if job.status in {PrintJob.STATUS_PENDING, PrintJob.STATUS_RENDERED}:
                return Response(
                    {"detail": "Este cupom ainda esta aguardando impressao."},
                    status=status.HTTP_409_CONFLICT,
                )
            job.status = PrintJob.STATUS_RENDERED
            job.error_message = ""
            job.printed_at = None
            job.updated_by = request.user
            job.save(update_fields=["status", "error_message", "printed_at", "updated_by", "updated_at"])
        return Response(PrintJobSerializer(job, context={"request": request}).data)
