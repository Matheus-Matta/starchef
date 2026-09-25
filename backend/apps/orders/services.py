import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.core.access import has_role_at_least
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.numbers import (
    MAX_QUANTITY,
    MAX_WEIGHT,
    parse_decimal,
    parse_money,
    parse_quantity,
)
from apps.core.tenant import tenant_context
from apps.customers.validators import is_valid_cpf, strip_cpf
from apps.orders.events import broadcast_kitchen_event
from apps.orders.command_billing import conclude_items_of_order
from apps.menu.models import ProductVariation
from apps.orders.item_cancellation import assert_pode_cancelar
from apps.orders.models import Order, OrderBatch, OrderItem, OrderItemAddon
from apps.restaurants.models import Command, Table

TWO_PLACES = Decimal("0.01")
THREE_PLACES = Decimal("0.001")


# A numeração do pedido mora em `order_numbering`. Reexportada porque
# `next_order_sequence` é chamado de fora e sempre foi importado daqui.
from apps.orders.order_numbering import (  # noqa: E402
    _criar_pedido_numerado,
)
from apps.orders.order_numbering import (  # noqa: E402
    next_order_sequence as next_order_sequence,
)


@transaction.atomic
def create_order(*, restaurant, order_type, user, branch=None, responsible_user=None, **kwargs):
    """Abre um pedido.

    [user] e quem gravou (auditoria); [responsible_user] e quem esta atendendo,
    quando os dois nao sao a mesma pessoa. E o caso do app do garcom: quem
    executa a operacao e o Caixa Principal, com as credenciais dele, mas quem
    atende a mesa e o garcom — e e o nome dele que a cozinha precisa ler na
    comanda.
    """
    account = restaurant.account

    with tenant_context(account):
        # Compatibilidade interna para importar histórico e gerar bases demo.
        # A API e as interfaces não expõem mais este tipo de abertura.
        if order_type == Order.TYPE_TABLE and kwargs.get("table"):
            table = Table.objects.select_for_update().get(pk=kwargs["table"].pk)
            if table.status == Table.STATUS_OCCUPIED and not table.current_order_id:
                raise ValidationError("A mesa está inconsistente: ocupada sem um pedido atual.")
            if table.status == Table.STATUS_OCCUPIED:
                raise ValidationError("A mesa já possui um pedido aberto.")
            kwargs["table"] = table

        if order_type == Order.TYPE_COMMAND and kwargs.get("command"):
            command = Command.objects.select_for_update().get(pk=kwargs["command"].pk)
            # DUAS CONTAS ABERTAS PARA O MESMO CARTÃO é o que não pode.
            #
            # Antes isto perguntava ao campo `status`, que hoje é calculado —
            # e calculado ele diz "em uso" também quando o cartão tem consumo
            # a cobrar, que é exatamente quando o caixa PRECISA abrir a conta.
            # A pergunta certa sempre foi sobre o pedido, não sobre o cartão.
            if Order.objects.filter(
                command_id=command.pk,
                status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
            ).exists():
                raise ValidationError("A comanda já está em uso.")
            kwargs["command"] = command
            # A mesa é um vínculo da comanda. O pedido guarda apenas o snapshot
            # para histórico, relatórios e impressão após o pagamento.
            kwargs["table"] = command.current_table

        # O PEDIDO HERDA OS CAMPOS DA COMANDA, e o que vem no corpo vence.
        #
        # O cartão foi aberto horas antes, no salão, e o código de quem o abriu
        # está nele. O pedido só nasce no caixa: sem herdar, o rastro do
        # atendimento inteiro sumiria justamente no registro que fica.
        #
        # O que vem no corpo não é sobrescrito porque é mais recente e mais
        # específico — ver `apps.core.metafields.herdar`.
        from apps.core.metafields import herdar
        from apps.orders.operator_code import exigir

        comanda = kwargs.get("command")
        kwargs["metafields"] = exigir(
            restaurant,
            herdar(kwargs.get("metafields"), getattr(comanda, "metafields", None)),
            acao="abrir pedido",
        )

        order = _criar_pedido_numerado(
            account=account,
            restaurant=restaurant,
            branch=None,
            order_type=order_type,
            responsible_user=responsible_user or user,
            created_by=user,
            updated_by=user,
            **kwargs,
        )

        if order.table_id:
            order.table.status = Table.STATUS_OCCUPIED
            order.table.current_order_id = order.id if order.order_type == Order.TYPE_TABLE else None
            order.table.save(update_fields=["status", "current_order_id", "updated_at"])

        if order.command_id:
            command = order.command
            # `status` não é gravado: ele responde pelo consumo pendente do
            # cartão, e abrir um pedido não consome nada — ver `Command.status`.
            command.current_order_id = order.id
            if order.customer_id and not command.customer_name:
                command.customer_name = order.customer.name
            command.save(update_fields=["current_order_id", "customer_name", "updated_at"])

        record_audit(action=AuditLog.ACTION_CREATED, instance=order, actor=user)
        return order


def _concluir_anotacao_do_item(item, *, when=None):
    """Um item de pedido saiu da conta: a anotação dele na comanda sai também.

    Nulo quando o item foi lançado direto no pedido (balcão, entrega, retirada)
    — aí não há cartão nenhum a atualizar.
    """
    if item.command_item_id is None:
        return
    from apps.orders.command_items import conclude_item

    conclude_item(item.command_item, when=when)


def free_command_for_order(order):
    """Devolve para a gaveta TODAS as comandas que este pedido cobrou.

    Um pedido pode ter incluído duzentos cartões — a mesa grande que paga
    junto é o caso, não a exceção. A liberação é por cartão e só acontece
    quando ele não tem mais nada pendente: outro garçom pode ter lançado uma
    sobremesa enquanto o caixa fechava a conta, e esse consumo não pode sumir.

    Assume estar dentro de transação/tenant_context do chamador.
    """
    from apps.orders.command_items import free_command_if_empty
    from apps.restaurants.models import Command

    ids = set(
        OrderItem.objects.filter(order_id=order.pk)
        .exclude(command_id__isnull=True)
        .values_list("command_id", flat=True)
    )
    if not ids:
        return
    # Ordenado por id: dois caixas fechando as mesmas mesas em ordens
    # diferentes é o formato clássico de impasse no banco.
    for command in Command.objects.filter(pk__in=ids).order_by("pk"):
        free_command_if_empty(command, user=order.updated_by)


def free_table_if_empty(table):
    """Libera a mesa quando nenhuma comanda está vinculada a ela.

    A mesa pode ter sido excluída entre a leitura e esta chamada — o gerente
    reorganiza o salão enquanto o garçom fecha a conta. `.get()` aqui levantava
    `DoesNotExist` e derrubava a operação inteira (500) por causa de uma mesa
    que já não existe e, justamente por isso, não precisa ser liberada.
    """
    if not table:
        return
    table = Table.objects.select_for_update().filter(pk=table.pk).first()
    if table is None:
        return
    active_commands = table.active_commands.exists()

    if not active_commands:
        table.status = Table.STATUS_FREE
        table.current_order_id = None
        table.save(update_fields=["status", "current_order_id", "updated_at"])


def _resolve_weighed_quantity(*, order, product, scale_reading=None, weight_kg=None, user=None):
    """Resolve a quantidade (em kg) de um produto pesavel a partir da balanca ou de peso manual."""
    from apps.printers.models import ScaleReading

    if scale_reading is not None:
        if scale_reading.account_id != order.account_id:
            raise ValidationError("Leitura de balanca pertence a outra conta.")
        if scale_reading.branch_id and order.branch_id and scale_reading.branch_id != order.branch_id:
            raise ValidationError("Leitura de balanca pertence a outra filial.")
        if scale_reading.order_item_id:
            raise ValidationError("Leitura de balanca ja foi usada em outro item.")
        max_age = scale_reading.scale.reading_max_age_seconds if scale_reading.scale_id else 120
        if scale_reading.created_at < timezone.now() - timedelta(seconds=max_age):
            raise ValidationError("Leitura de balanca expirada. Pese novamente.")
        net = scale_reading.net_weight_kg
        if net <= 0:
            raise ValidationError("Peso liquido invalido na leitura da balanca.")
        return Decimal(net).quantize(THREE_PLACES), scale_reading

    if weight_kg is not None:
        # Peso vem do corpo (o PDV manda o peso bruto no replay offline da
        # balança): texto ou número absurdo aqui não pode virar 500.
        weight_kg = parse_decimal(
            weight_kg, field="weight_kg", maximum=MAX_WEIGHT
        ).quantize(THREE_PLACES)
        if weight_kg <= 0:
            raise ValidationError("Peso deve ser maior que zero.")
        # Registra leitura manual para auditoria da pesagem.
        manual_reading = ScaleReading.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            scale=None,
            weight_kg=weight_kg,
            tare_kg=Decimal("0"),
            source=ScaleReading.SOURCE_MANUAL,
            created_by=user,
            updated_by=user,
        )
        return weight_kg, manual_reading

    raise ValidationError(f"Produto '{product.name}' e vendido por peso: informe a leitura da balanca ou o peso em kg.")


@transaction.atomic
def add_order_item(
    *,
    order,
    product,
    quantity=None,
    user,
    variations=None,
    addons=None,
    customer_note="",
    scale_reading=None,
    weight_kg=None,
    expected_unit_price=None,
    metafields=None,
):
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        # O CÓDIGO DE QUEM LANÇOU, quando o restaurante exige. O item herda o que
        # o pedido tiver: quem abriu a conta já se identificou, e cobrar o código
        # a cada prato faria o garçom digitar dez vezes no mesmo atendimento.
        #
        # A conferência vem ANTES das outras: barrar por falta de código depois de
        # resolver peso, variação e adicional gastaria as consultas para nada.
        from apps.core.metafields import herdar
        from apps.orders.operator_code import exigir

        extras = exigir(
            order.restaurant,
            herdar(metafields, order.metafields),
            acao="lançar item",
        )
        if product.account_id != order.account_id:
            raise ValidationError("O produto não pertence à conta do pedido.")
        if not product.restaurants.filter(pk=order.restaurant_id).exists():
            raise ValidationError("O produto não está disponível neste restaurante.")
        if order.is_locked:
            raise ValidationError("Pedidos pagos, cancelados ou estornados não podem ser alterados.")
        # A lista que o caixa esta lendo em voz alta para o cliente nao pode
        # mudar embaixo dele — e um item lancado agora ficaria fora do
        # pagamento, que e o pior defeito possivel aqui: a comida sai e
        # ninguem cobra.
        if not product.is_active:
            raise ValidationError("Um produto inativo não pode ser adicionado ao pedido.")

        reading_to_link = None
        if product.is_weighed:
            quantity, reading_to_link = _resolve_weighed_quantity(
                order=order,
                product=product,
                scale_reading=scale_reading,
                weight_kg=weight_kg,
                user=user,
            )
        else:
            if scale_reading is not None or weight_kg is not None:
                raise ValidationError(f"Produto '{product.name}' e vendido por unidade e nao aceita peso.")
            # `Decimal(str(...))` cru estourava `InvalidOperation` (500) com
            # "duas" no campo, e deixava passar 10^30 para morrer no INSERT.
            quantity = parse_quantity(quantity, default=1)

        variation_ids = [entry.get("id") if isinstance(entry, dict) else entry for entry in (variations or [])]
        variation_ids = [value for value in variation_ids if value]
        selected_variations = list(
            ProductVariation.objects.filter(product=product, is_active=True, id__in=variation_ids).order_by("id")
        )
        if len(selected_variations) != len(set(map(str, variation_ids))):
            raise ValidationError("Uma ou mais variacoes nao pertencem ao produto.")
        if product.requires_variation and not selected_variations:
            raise ValidationError("Selecione uma variacao obrigatoria.")

        addon_ids = [entry.get("id") if isinstance(entry, dict) else entry for entry in (addons or [])]
        addon_ids = [value for value in addon_ids if value]
        selected_addons = list(product.addons.filter(is_active=True, id__in=addon_ids).order_by("id"))
        if len(selected_addons) != len(set(map(str, addon_ids))):
            raise ValidationError("Um ou mais adicionais nao pertencem ao produto.")

        variation_snapshot = [
            {"id": str(v.id), "name": v.name, "price_delta": str(v.price_delta)} for v in selected_variations
        ]
        extras_price = sum((v.price_delta for v in selected_variations), Decimal("0.00"))
        extras_price += sum((a.price for a in selected_addons), Decimal("0.00"))
        unit_price = product.current_price + extras_price
        if expected_unit_price not in (None, ""):
            expected = parse_money(
                expected_unit_price, field="expected_unit_price"
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            actual = unit_price.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if expected != actual:
                raise ValidationError(
                    "O preço deste item mudou desde que o PDV ficou offline. "
                    "Revise o pedido antes de continuar a sincronização."
                )

        existing = None
        if not product.is_weighed:
            candidates = (
                OrderItem.objects.select_for_update()
                .filter(
                    order=order,
                    product=product,
                    status=OrderItem.STATUS_PENDING,
                    customer_note=customer_note,
                    variations=variation_snapshot,
                )
                .prefetch_related("addons")
            )
            selected_addon_ids = {str(a.id) for a in selected_addons}
            existing = next(
                (
                    candidate
                    for candidate in candidates
                    if {str(a.addon_id) for a in candidate.addons.all()} == selected_addon_ids
                ),
                None,
            )
        if existing is not None:
            existing.quantity += quantity
            existing.unit_price = unit_price
            existing.total_price = (unit_price * existing.quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            existing.updated_by = user
            existing.save(update_fields=["quantity", "unit_price", "total_price", "updated_by", "updated_at"])
            for item_addon in existing.addons.all():
                item_addon.total_price = (item_addon.unit_price * existing.quantity).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                item_addon.updated_by = user
                item_addon.save(update_fields=["total_price", "updated_by", "updated_at"])
            recalculate_order(order)
            return existing

        item = OrderItem.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            order=order,
            # DE QUEM E O ITEM, gravado no lancamento. Depois da consolidacao
            # todos os itens vivem no mesmo pedido: se a comanda nao estiver
            # aqui, "de quem e este prato" se perde — na conferencia com o
            # cliente e na cozinha.
            command=order.command,
            product=product,
            quantity=quantity,
            unit_price=unit_price,
            total_price=(unit_price * quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            variations=variation_snapshot,
            customer_note=customer_note,
            production_sector=product.production_sector,
            launched_by=user,
            created_by=user,
            updated_by=user,
            metafields=extras,
        )
        for addon in selected_addons:
            OrderItemAddon.objects.create(
                account=order.account,
                restaurant=order.restaurant,
                branch=order.branch,
                item=item,
                addon=addon,
                quantity=1,
                unit_price=addon.price,
                total_price=addon.price * quantity,
                created_by=user,
                updated_by=user,
            )
        if reading_to_link is not None:
            reading_to_link.order_item = item
            reading_to_link.save(update_fields=["order_item", "updated_at"])
        recalculate_order(order)
        record_audit(action=AuditLog.ACTION_CREATED, instance=item, actor=user)
        return item


@transaction.atomic
def recalculate_order(order):
    """Reprojeta subtotal, taxa de servico e total a partir dos itens de agora.

    A taxa acompanha o subtotal sempre que ela nasceu de um percentual
    (`service_fee_percent`). Antes ela ficava congelada no valor calculado no
    fechamento: qualquer item que chegasse depois — e a fila offline do PDV
    entrega itens depois do fechamento com frequencia, seja por ordem de fila,
    seja porque um item recusado por preco subiu ja corrigido — aumentava o
    subtotal sem aumentar a taxa. O total do servidor deixava de ser
    "subtotal + 10%" e divergia, centavo a centavo ou real a real, do total que
    o PDV mostrou e cobrou do cliente.

    Taxa digitada a mao pelo gerente nao tem percentual e continua intocada: ali
    o valor E a decisao, nao um derivado.
    """
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        excluded = {OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED}
        subtotal = order.items.exclude(status__in=excluded).aggregate(value=Sum("total_price"))["value"]
        order.subtotal = subtotal or Decimal("0.00")
        order.service_fee = service_fee_for(order)
        # O CUPOM E REAVALIADO AQUI, a cada recalculo. Um cupom de "acima de
        # R$ 50" aplicado num pedido de R$ 60 tem de cair quando o operador
        # remove metade dos itens: congelar o abatimento no momento da aplicacao
        # e como se da desconto sem querer, e ninguem revisa um total que ja
        # apareceu certo na tela uma vez.
        from apps.promotions.coupon_service import revalidar

        order.coupon_discount, _caiu = revalidar(order)
        order.total = (
            order.subtotal
            + order.service_fee
            + order.delivery_fee
            - order.discount
            - order.coupon_discount
        )
        if order.total < Decimal("0.00"):
            order.total = Decimal("0.00")
        order.save(update_fields=["subtotal", "service_fee", "coupon_discount", "total", "updated_at"])
        return order


def service_fee_for(order):
    """Taxa de servico que corresponde ao subtotal atual do pedido.

    O arredondamento acontece AQUI, e nao no campo do banco: SQLite nao trunca
    `DecimalField` como o Postgres, e o PDV soma a taxa ja arredondada. Deixar
    o arredondamento para a gravacao fazia os dois lados discordarem por um
    centavo.
    """
    if not order.service_fee_enabled:
        return Decimal("0.00")
    if order.service_fee_percent is None:
        return order.service_fee
    return ((order.subtotal * order.service_fee_percent) / Decimal("100")).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )


@transaction.atomic
def send_order_to_kitchen(order, user, *, client_batch_serial=None, offline_printed=False):
    """Send pending items to production and release printing immediately.

    ``client_batch_serial``/``offline_printed`` existem para o PDV que já
    imprimiu a comanda localmente porque a rede estava fora: o serial garante
    que o `REF:` do ticket impresso offline bate com este lote, e a flag evita
    que o backend gere um segundo `PrintJob` de verdade para o mesmo pedido.
    """
    with tenant_context(order.account):
        order = Order.objects.select_for_update().prefetch_related("items__product").get(pk=order.pk)
        if order.is_locked:
            raise ValidationError("Pedidos bloqueados não podem ser enviados para a cozinha.")

        items = list(order.items.filter(status=OrderItem.STATUS_PENDING))
        if not items:
            raise ValidationError("Não há itens pendentes para enviar à cozinha.")

        now = timezone.now()
        # Carência do restaurante: a rodada nasce agendada e só chega ao KDS e
        # à impressora quando `dispatch_at` vencer (task `orders.dispatch_due_
        # kitchen_batches` ou o fallback de leitura do KDS). Até lá, cancelar
        # é de graça — nada chegou à produção. Comanda já impressa no terminal
        # (`offline_printed`) não espera: o papel já saiu.
        grace_seconds = int(getattr(order.restaurant, "cancellation_grace_seconds", 0) or 0)
        if offline_printed:
            grace_seconds = 0
        dispatch_at = now + timedelta(seconds=grace_seconds) if grace_seconds > 0 else now

        batch_serial = None
        if client_batch_serial:
            try:
                batch_serial = uuid.UUID(str(client_batch_serial))
            except (ValueError, AttributeError, TypeError):
                batch_serial = None

        # Each send creates a new production round
        last_batch_number = order.batches.aggregate(value=Max("batch_number"))["value"] or 0
        batch = OrderBatch.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            order=order,
            batch_number=last_batch_number + 1,
            status=OrderBatch.STATUS_SCHEDULED,
            sent_at=now,
            dispatch_at=dispatch_at,
            sent_by=user,
            created_by=user,
            updated_by=user,
            **({"serial": batch_serial} if batch_serial else {}),
        )

        for item in items:
            item.status = OrderItem.STATUS_QUEUED
            item.batch = batch
            item.sent_to_kitchen_at = None
            item.updated_by = user
            item.save(update_fields=["status", "batch", "sent_to_kitchen_at", "updated_by", "updated_at"])

        order.updated_by = user
        order.save(update_fields=["updated_by", "updated_at"])
        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=order,
            actor=user,
            metadata={
                "event": "kitchen_dispatch_requested",
                "batch": batch.batch_number,
                "batch_serial": str(batch.serial),
                "dispatch_at": dispatch_at.isoformat(),
                "immediate": grace_seconds == 0,
                "grace_seconds": grace_seconds,
            },
        )

        from apps.printers.services import register_kitchen_batch_print_jobs

        register_kitchen_batch_print_jobs(batch=batch, user=user, offline_printed=offline_printed)

        dispatch_kitchen_batch(batch, now=now)
        order.refresh_from_db()

        return order


@transaction.atomic
def create_order_with_item(
    *,
    restaurant,
    order_type,
    product,
    user,
    command=None,
    table=None,
    item_data=None,
    responsible_user=None,
):
    """Atomically creates a real order only when its first item is valid."""
    item_data = dict(item_data or {})
    with tenant_context(restaurant.account):
        if command is not None and table is not None:
            command = Command.objects.select_for_update().get(pk=command.pk)
            table = Table.objects.select_for_update().get(pk=table.pk)
            if table.restaurant_id != restaurant.id or table.status == Table.STATUS_CLEANING:
                raise ValidationError("A mesa selecionada não está disponível neste restaurante.")
            if command.current_table_id != table.id:
                from apps.restaurants.services import assert_table_accepts_commands

                assert_table_accepts_commands(table, restaurant=restaurant, exclude_command_ids=[command.pk])
            old_table_id = command.current_table_id
            command.current_table = table
            command.branch = table.branch
            command.updated_by = user
            command.save(update_fields=["current_table", "branch", "updated_by", "updated_at"])
            table.status = Table.STATUS_OCCUPIED
            table.current_order_id = None
            table.save(update_fields=["status", "current_order_id", "updated_at"])

            from apps.restaurants.models import CommandMovementLog

            CommandMovementLog.objects.create(
                account=command.account,
                restaurant=command.restaurant,
                branch=command.branch,
                command=command,
                action=CommandMovementLog.ACTION_LINKED,
                table=table,
                from_table_id=old_table_id,
                waiter=user,
            )
            if old_table_id and old_table_id != table.id:
                free_table_if_empty(Table.objects.filter(pk=old_table_id).first())

        order = create_order(
            restaurant=restaurant,
            order_type=order_type,
            command=command,
            # A MESA TAMBÉM VAI. A view já a conferiu (restaurante, ativa) e
            # devolve 400 para uma mesa inválida — conferir e depois descartar
            # é o pior dos dois mundos: a chamada diz "esta conta é da mesa 7",
            # o servidor concorda e grava o pedido sem mesa nenhuma.
            #
            # Sem isso, a conta agrupada aberta sobre a mesa nascia solta: a
            # mesa não ficava ocupada, o cupom não dizia de onde era, e
            # `free_table_if_empty(order.table)` no pagamento não tinha o que
            # liberar. Com comanda informada, `create_order` sobrescreve com a
            # mesa DO CARTÃO — é ela que manda no vínculo.
            table=table,
            user=user,
            responsible_user=responsible_user,
            # O CODIGO DO OPERADOR SOBE COM O PEDIDO, e nao so com o item. Sem
            # isso, `create_order` recusaria a abertura por falta de codigo num
            # restaurante que o exige — e o item que o trazia nunca chegaria a
            # ser criado.
            metafields=item_data.get("metafields"),
        )
        add_order_item(order=order, product=product, user=user, **item_data)
        return Order.objects.prefetch_related("items__product", "items__addons", "items__batch").get(pk=order.pk)


@transaction.atomic
def dispatch_kitchen_batch(batch, *, now=None):
    """Release a scheduled round to KDS/printers after the grace period."""
    now = now or timezone.now()
    with tenant_context(batch.account):
        batch = (
            OrderBatch.objects.select_related("order__restaurant", "sent_by")
            # `sent_by` is nullable. PostgreSQL rejects FOR UPDATE on the
            # nullable side of the LEFT JOIN unless the locked table is scoped.
            .select_for_update(of=("self",))
            .get(pk=batch.pk)
        )
        if batch.status != OrderBatch.STATUS_SCHEDULED:
            return batch
        if batch.dispatch_at and batch.dispatch_at > now:
            return batch

        items = list(
            batch.items.select_related("order", "product")
            .select_for_update(of=("self",))
            .filter(status=OrderItem.STATUS_QUEUED)
        )
        if not items:
            batch.status = OrderBatch.STATUS_CANCELLED
            batch.save(update_fields=["status", "updated_at"])
            from apps.printers.models import PrintJob

            PrintJob.objects.filter(
                payload__batch_id=str(batch.id),
                status=PrintJob.STATUS_SCHEDULED,
            ).update(status=PrintJob.STATUS_CANCELLED, updated_at=now)
            return batch

        for item in items:
            item.status = OrderItem.STATUS_SENT
            item.sent_to_kitchen_at = now
            item.save(update_fields=["status", "sent_to_kitchen_at", "updated_at"])
            transaction.on_commit(
                lambda current=item: broadcast_kitchen_event(
                    current.account_id,
                    current.branch_id,
                    current.production_sector,
                    "order_item.sent",
                    serialize_kitchen_item(current),
                )
            )

        batch.status = OrderBatch.STATUS_SENT
        batch.sent_at = now
        batch.save(update_fields=["status", "sent_at", "updated_at"])

        order = batch.order
        order.production_status = Order.PROD_SENT
        order.updated_by = batch.sent_by
        order.save(update_fields=["production_status", "updated_by", "updated_at"])

        # DEPOIS DE UMA CONSOLIDACAO o lote fica na origem como historia de
        # producao, mas os itens ja pertencem ao pedido final. O quadro e o
        # resumo por pedido leem `item.order`: sem avancar o destino tambem,
        # a comida some do pedido que o cliente esta pagando.
        destinos = {
            item.order_id for item in items if item.order_id and item.order_id != order.id
        }
        for destino_id in sorted(str(value) for value in destinos):
            destino = Order.objects.select_for_update().filter(pk=destino_id).first()
            if destino is None or destino.production_status != Order.PROD_IDLE:
                continue
            destino.production_status = Order.PROD_SENT
            destino.save(update_fields=["production_status", "updated_at"])

        from apps.printers.models import PrintJob

        PrintJob.objects.filter(
            payload__batch_id=str(batch.id),
            status=PrintJob.STATUS_SCHEDULED,
        ).update(status=PrintJob.STATUS_RENDERED, available_at=now, updated_at=now)

        if order.restaurant.stock_deduction_timing == "kitchen":
            from apps.stock.services import deduct_order_stock

            # A BAIXA E DO LOTE, nao do pedido. Quando a comanda ja entrou numa
            # conta agrupada, `order.items` do pedido de origem esta vazio e a
            # baixa nao encontrava nada para dar: a cozinha recebia o prato e o
            # insumo continuava no estoque.
            deduct_order_stock(order=order, user=batch.sent_by, items=batch.items)

        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=order,
            actor=batch.sent_by,
            metadata={
                "event": "kitchen_dispatch_released",
                "batch": batch.batch_number,
                "batch_serial": str(batch.serial),
            },
        )
        return batch


def dispatch_due_kitchen_batches(*, account_id=None, restaurant_id=None, now=None):
    """Release all due rounds; safe for Celery and read-time fallback."""
    now = now or timezone.now()
    due = OrderBatch.all_objects.filter(
        status=OrderBatch.STATUS_SCHEDULED,
        dispatch_at__lte=now,
        deleted_at__isnull=True,
    )
    if account_id:
        due = due.filter(account_id=account_id)
    if restaurant_id:
        due = due.filter(restaurant_id=restaurant_id)
    batch_ids = list(due.values_list("id", flat=True)[:500])
    for batch_id in batch_ids:
        batch = OrderBatch.all_objects.select_related("account").get(pk=batch_id)
        dispatch_kitchen_batch(batch, now=now)
    return len(batch_ids)


@transaction.atomic
def set_order_item_quantity(item, user, quantity):
    """Ajusta a quantidade de um item que ainda NAO foi para a producao.

    Existe para o `+` e o `-` do teclado do PDV. So item pendente entra aqui:
    um item ja despachado descreve o que a cozinha recebeu, e mudar a
    quantidade dele reescreveria o passado sem que ninguem na producao ficasse
    sabendo — para esse caso existem o cancelamento e a cortesia, que avisam.

    Quantidade zero seria um item invisivel com preco; quem quer remover usa
    `void_order_item`, que exige motivo e deixa registro.
    """
    quantity = parse_decimal(quantity, field="quantity", maximum=MAX_QUANTITY)
    if quantity <= 0:
        raise ValidationError("Para remover o item, cancele-o informando o motivo.")

    with tenant_context(item.account):
        item = (
            OrderItem.objects.select_related("order", "product")
            .select_for_update(of=("self",))
            .get(pk=item.pk)
        )
        if item.order.is_locked:
            raise ValidationError("Itens de pedidos pagos, cancelados ou estornados não podem ser alterados.")
        if item.status != OrderItem.STATUS_PENDING:
            raise ValidationError(
                "Só um item que ainda não foi para a produção pode ter a quantidade alterada."
            )
        if item.product_id and item.product.is_weighed:
            raise ValidationError(
                "Produto vendido por peso: a quantidade vem da balança, não do teclado."
            )

        item.quantity = quantity
        item.total_price = (item.unit_price * quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        item.updated_by = user
        item.save(update_fields=["quantity", "total_price", "updated_by", "updated_at"])
        for item_addon in item.addons.all():
            item_addon.total_price = (item_addon.unit_price * quantity).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            item_addon.updated_by = user
            item_addon.save(update_fields=["total_price", "updated_by", "updated_at"])
        recalculate_order(item.order)
        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=item,
            actor=user,
            metadata={"event": "item_quantity_changed", "quantity": str(quantity)},
        )
        return item


def void_order_item(item, user, reason="", offline_printed=False, authorized=False,
                    authorized_by=None):
    """Cancela um item, com cupom de cancelamento so depois de despachado.

    ``offline_printed=True`` vem do PDV que ja imprimiu o cupom na impressora
    do setor porque a operacao ficou na fila local. O job continua sendo
    criado para a auditoria, mas ja nasce impresso — senao o agente local
    imprimiria o mesmo cancelamento de novo ao sincronizar.
    """
    if not reason.strip():
        raise ValidationError("Informe o motivo do cancelamento do item.")
    with tenant_context(item.account):
        item = (
            OrderItem.objects.select_related("order", "batch")
            .select_for_update(of=("self",))
            .get(pk=item.pk)
        )
        if item.order.is_locked:
            raise ValidationError("Itens de pedidos pagos, cancelados ou estornados não podem ser alterados.")
        if item.status in {OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED}:
            raise ValidationError("Este item já foi cancelado ou retirado da conta.")

        within_grace = item.status == OrderItem.STATUS_QUEUED
        if within_grace and item.batch and item.batch.dispatch_at and item.batch.dispatch_at <= timezone.now():
            dispatch_kitchen_batch(item.batch)
            item.refresh_from_db()
            within_grace = item.status == OrderItem.STATUS_QUEUED

        # DEPOIS de liberar o lote vencido, e não antes: um lote agendado que
        # já passou da hora conta como despachado, e é desse instante que a
        # janela de cancelamento corre. Checar antes mediria o tempo errado.
        assert_pode_cancelar(item, authorized=authorized)

        was_dispatched = item.status not in {OrderItem.STATUS_PENDING, OrderItem.STATUS_QUEUED}
        item.status = OrderItem.STATUS_CANCELLED
        item.void_reason = reason
        item.voided_at = timezone.now()
        item.voided_by = user
        item.updated_by = user
        item.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_by", "updated_at"])
        # Cancelar na cozinha e sair da comanda sao coisas diferentes, mas um
        # item cancelado precisa sair da comanda TAMBEM: senao ele continua
        # ocupando o cartao do proximo cliente.
        _concluir_anotacao_do_item(item, when=item.voided_at)
        recalculate_order(item.order)
        if within_grace and item.batch_id:
            from apps.printers.services import refresh_scheduled_kitchen_batch_jobs

            refresh_scheduled_kitchen_batch_jobs(batch=item.batch, user=user)
        elif was_dispatched:
            from apps.printers.services import register_kitchen_item_cancellation_jobs

            register_kitchen_item_cancellation_jobs(
                item=item, user=user, reason=reason, offline_printed=offline_printed
            )
        record_audit(
            action=AuditLog.ACTION_CANCELLED,
            instance=item,
            actor=user,
            reason=reason,
            metadata={
                # QUEM LIBEROU fica gravado. Sem isto o registro diz apenas que
                # o operador cancelou, e a pergunta que o dono faz depois —
                # "quem autorizou tirar isso da conta?" — fica sem resposta.
                **({"authorized_by": str(authorized_by.pk)} if authorized_by else {}),
                "event": "order_item_cancelled",
                "within_print_grace_period": within_grace,
                "cancellation_ticket_required": was_dispatched,
            },
        )
        return item


@transaction.atomic
def comp_order_item(item, user, reason=""):
    """Mark a sent/in-production item as comped (courtesy) — does not deduct from bill."""
    with tenant_context(item.account):
        item = OrderItem.objects.select_related("order").select_for_update(of=("self",)).get(pk=item.pk)
        if item.order.is_locked:
            raise ValidationError("Itens de pedidos pagos, cancelados ou estornados não podem ser alterados.")
        if item.status in {OrderItem.STATUS_PENDING, OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED}:
            raise ValidationError(
                "A cortesia só pode ser aplicada a itens já enviados à cozinha. Cancele itens que ainda estão pendentes."
            )

        if not has_role_at_least(user, "manager"):
            raise ValidationError("Aplicar cortesia exige permissão de gerente.")

        item.status = OrderItem.STATUS_COMPED
        item.void_reason = reason
        item.voided_at = timezone.now()
        item.voided_by = user
        item.updated_by = user
        item.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_by", "updated_at"])
        _concluir_anotacao_do_item(item, when=item.voided_at)
        recalculate_order(item.order)
        record_audit(
            action=AuditLog.ACTION_UPDATED, instance=item, actor=user, reason=reason, metadata={"event": "comp"}
        )
        return item


# Avancos de PRODUCAO (o que o KDS faz). Nao mudam composicao nem valor do
# pedido, entao continuam liberados depois do pagamento.
_KITCHEN_STATUSES = frozenset(
    {OrderItem.STATUS_PREPARING, OrderItem.STATUS_READY, OrderItem.STATUS_DELIVERED}
)


@transaction.atomic
def update_order_item_status(item, new_status, user, reason=""):
    with tenant_context(item.account):
        item = OrderItem.objects.select_related("order").select_for_update(of=("self",)).get(pk=item.pk)
        # Cancelado/estornado e ponto final: nao ha producao a fazer.
        if item.order.status in {Order.STATUS_CANCELLED, Order.STATUS_REFUNDED}:
            raise ValidationError("Itens de pedidos cancelados ou estornados não podem ser alterados.")
        # Pago NAO trava a cozinha: o caixa cobra assim que manda os itens para a
        # producao, entao "pago com comida na chapa" e o estado normal de um card
        # no KDS. O bloqueio existe para o que mexe na composicao/valor do pedido
        # (cancelar item, cortesia), nao para o cozinheiro avancar a ficha —
        # producao e um ciclo independente do financeiro (Order.production_status).
        if item.order.status == Order.STATUS_PAID and new_status not in _KITCHEN_STATUSES:
            raise ValidationError(
                "Pedido já pago: a cozinha pode avançar a produção, mas o item não pode mais ser alterado."
            )

        # Guard special transitions through dedicated functions
        if new_status == OrderItem.STATUS_CANCELLED:
            return void_order_item(item, user, reason)
        if new_status == OrderItem.STATUS_COMPED:
            return comp_order_item(item, user, reason)
        if item.status == OrderItem.STATUS_QUEUED:
            raise ValidationError(
                "O item ainda está sendo liberado para produção. Atualize e tente novamente."
            )

        if item.status == OrderItem.STATUS_READY and new_status != OrderItem.STATUS_DELIVERED:
            if not has_role_at_least(user, "manager"):
                raise ValidationError("Alterar itens prontos exige permissão de gerente.")

        now = timezone.now()
        item.status = new_status
        item.updated_by = user
        if new_status == OrderItem.STATUS_PREPARING:
            item.preparation_started_at = now
        elif new_status == OrderItem.STATUS_READY:
            item.ready_at = now
        elif new_status == OrderItem.STATUS_DELIVERED:
            item.delivered_at = now

        item.save()
        recalculate_order(item.order)
        sync_production_status(item.order)
        record_audit(
            action=AuditLog.ACTION_UPDATED, instance=item, actor=user, reason=reason, metadata={"status": new_status}
        )
        broadcast_kitchen_event(
            item.account_id,
            item.branch_id,
            item.production_sector,
            "order_item.status_changed",
            serialize_kitchen_item(item),
        )
        return item


@transaction.atomic
def close_order(
    order,
    user,
    *,
    discount=Decimal("0.00"),
    service_fee=None,
    service_fee_enabled=None,
    fiscal_customer_cpf=None,
    expected_total=None,
    coupon_code=None,
):
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.is_locked:
            raise ValidationError("Pedidos bloqueados não podem ser fechados.")
        # O valor pode chegar como str/float/int (corpo da requisição) — normaliza
        # para Decimal antes de comparar/gravar. Negativo fica de fora: a guarda
        # era `> 0`, então um desconto de -50 passava direto e AUMENTAVA o total
        # do pedido, sem exigir gerente e sem aparecer em lugar nenhum.
        discount = parse_money(discount, field="discount", default=0)
        if discount > Decimal("0.00"):
            if not has_role_at_least(user, "manager"):
                raise ValidationError("Aplicar desconto exige permissão de gerente.")
        # Desconto maior que a mercadoria era aceito e o total ia a zero pelo
        # `max(0)` do recálculo: a venda ficava registrada com um desconto que
        # nunca existiu, e o relatório de descontos deixava de fechar com o
        # faturamento. Dar a mercadoria inteira é o teto.
        if discount > order.subtotal:
            raise ValidationError(
                {"discount": "O desconto não pode ser maior que o subtotal do pedido."}
            )

        order.discount = discount
        if fiscal_customer_cpf is not None:
            normalized_cpf = strip_cpf(str(fiscal_customer_cpf))
            if normalized_cpf and not is_valid_cpf(normalized_cpf):
                raise ValidationError("Informe um CPF valido para incluir na NFC-e.")
            order.fiscal_customer_cpf = normalized_cpf
        # O CUPOM ENTRA DEPOIS DO CPF, e nao antes: a regra de "um por cliente"
        # e a de grupo se resolvem pelo CPF da nota, e avaliar o cupom antes de
        # gravar o CPF recusaria quem acabou de informa-lo.
        #
        # `None` significa "nao mexe"; string vazia significa "retira". Sao
        # gestos diferentes: fechar o pedido de novo para corrigir a taxa nao
        # pode derrubar o cupom que ja estava aplicado.
        if coupon_code is not None:
            from apps.promotions.coupon_service import aplicar_cupom, retirar_cupom

            if str(coupon_code).strip():
                aplicar_cupom(order, coupon_code)
            else:
                retirar_cupom(order)
        if service_fee_enabled is not None:
            if isinstance(service_fee_enabled, str):
                service_fee_enabled = service_fee_enabled.lower() in {"1", "true", "yes", "on"}
            order.service_fee_enabled = bool(service_fee_enabled)
        # A ALIQUOTA e o que fica gravado, nao apenas o valor: `recalculate_order`
        # refaz a taxa a partir dela toda vez que o subtotal muda, e e isso que
        # mantem o total do servidor igual ao que o PDV cobrou quando um item
        # chega depois do fechamento.
        if not order.service_fee_enabled:
            order.service_fee_percent = None
            order.service_fee = Decimal("0.00")
        elif service_fee is not None:
            # Valor digitado: nao e derivado de percentual nenhum e nao pode ser
            # reescrito pelo recalculo.
            order.service_fee_percent = None
            order.service_fee = parse_money(
                service_fee, field="service_fee", default=0
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            order.service_fee_percent = order.restaurant.default_service_fee_percent or Decimal("0.00")
            order.service_fee = service_fee_for(order)
        order.status = Order.STATUS_AWAITING_PAYMENT
        order.closed_by = user
        order.updated_by = user
        order.closed_at = timezone.now()
        order.save(
            update_fields=[
                "discount",
                "service_fee",
                "service_fee_enabled",
                "service_fee_percent",
                "fiscal_customer_cpf",
                "status",
                "closed_by",
                "closed_at",
                "updated_by",
            ]
        )
        order = recalculate_order(order)
        expected = None
        if expected_total not in (None, ""):
            # Conferência de concorrência, não autoridade sobre o preço — mas o
            # valor vem do corpo, então texto aqui também derrubava o fechamento.
            expected = parse_money(
                expected_total, field="expected_total", allow_negative=True
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        actual_total = order.total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        # `expected_total` é diagnóstico de concorrência, não autoridade sobre
        # o preço. Todas as mutações anteriores já passaram pelas próprias
        # validações e o servidor acabou de recalcular a venda sob lock; rejeitar
        # aqui deixava o PDV preso tentando adivinhar o mesmo arredondamento.
        # O fechamento segue com o total autoritativo e a resposta informa a
        # reconciliação para a tela atualizar antes de receber o pagamento.
        order._client_expected_total = expected
        order._total_reconciled = expected is not None and expected != actual_total

        # Fechar novamente um pedido parcialmente pago pode alterar desconto ou
        # taxa. O estado financeiro precisa acompanhar o novo total; caso
        # contrário a interface mostra saldo zero enquanto o pedido permanece
        # parcial no servidor.
        from apps.payments.models import Payment

        paid_total = order.payments.filter(status=Payment.STATUS_APPROVED).aggregate(value=Sum("amount"))[
            "value"
        ] or Decimal("0.00")
        if paid_total > order.total:
            raise ValidationError(
                "A alteração deixaria o valor já pago maior que o total do pedido. "
                "Cancele ou ajuste os pagamentos antes de retirar a taxa."
            )
        paid_in_full = paid_total == order.total and order.total > Decimal("0.00")
        if paid_in_full:
            order.payment_status = Order.PAYMENT_PAID
            order.status = Order.STATUS_PAID
        elif paid_total > Decimal("0.00"):
            order.payment_status = Order.PAYMENT_PARTIAL
        else:
            order.payment_status = Order.PAYMENT_PENDING
        order.save(update_fields=["payment_status", "status", "updated_by"])
        if paid_in_full:
            # O RESGATE DO CUPOM NASCE AQUI, no pagamento — nunca na aplicação.
            # Gravado na aplicação, um cupom de compra única queimaria num pedido
            # abandonado e o cliente perderia o direito sem ter comprado nada.
            from apps.promotions.coupon_service import registrar_resgate

            registrar_resgate(order)
            # Pago: as anotações saem da comanda como VENDA.
            conclude_items_of_order(order, billed=True)
            if order.table_id:
                free_table_if_empty(order.table)
            free_command_for_order(order)
            if order.restaurant.stock_deduction_timing == "payment":
                from apps.stock.services import deduct_order_stock

                deduct_order_stock(order=order, user=user)
        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=order,
            actor=user,
            metadata={
                "event": "close_order",
                "total_reconciled": order._total_reconciled,
                "client_expected_total": str(expected) if expected is not None else None,
                "authoritative_total": str(actual_total),
            },
        )
        return order


@transaction.atomic
def order_is_empty(order):
    """O pedido nao tem nada que valha guardar?

    Sem item que conte e sem recebimento aprovado, ele e so uma comanda
    ocupada: nao ha o que auditar, nao ha o que estornar, e a mesa/comanda
    fica presa para o proximo cliente. Cortesia e item ja cancelado nao
    contam — eles nao deixam a venda "com conteudo".
    """
    with tenant_context(order.account):
        has_items = (
            order.items.exclude(
                status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED]
            )
            .exists()
        )
        has_payments = order.payments.filter(status="approved").exists()
        return not has_items and not has_payments


# Itens que ainda não chegaram à produção: nunca enviados ou enviados dentro
# da carência (rodada agendada, KDS e impressora ainda não viram).
_ITEM_STATUSES_NOT_IN_PRODUCTION = {
    OrderItem.STATUS_PENDING,
    OrderItem.STATUS_QUEUED,
    OrderItem.STATUS_CANCELLED,
    OrderItem.STATUS_COMPED,
}


def order_within_cancellation_grace(order):
    """Cancelar este pedido agora dispensa autorização?

    Verdadeiro quando o restaurante tem carência configurada e nenhum item
    chegou à produção. Antes de decidir, libera as rodadas vencidas: um
    lote agendado há mais tempo que a carência já é da cozinha.
    """
    grace = int(getattr(order.restaurant, "cancellation_grace_seconds", 0) or 0)
    if grace <= 0:
        return False
    if order.batches.filter(status=OrderBatch.STATUS_SCHEDULED, dispatch_at__lte=timezone.now()).exists():
        dispatch_due_kitchen_batches(restaurant_id=order.restaurant_id)
    return not order.items.exclude(status__in=_ITEM_STATUSES_NOT_IN_PRODUCTION).exists()


@transaction.atomic
def cancel_order(order, user, reason, authorized_by=None, authorization=None):
    # Pedido vazio é descarte; exigir justificativa ensina a escrever qualquer coisa.
    if not reason and order_is_empty(order):
        reason = "Pedido vazio descartado"
    if not reason:
        raise ValidationError("O motivo do cancelamento é obrigatório.")
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == Order.STATUS_CANCELLED:
            return order
        pagamento_integral = order.payment_status == Order.PAYMENT_PAID
        from apps.invoices.order_cancellation import cancel_invoice_for_order
        cancel_invoice_for_order(order, reason=reason, user=user)
        from apps.payments.models import Payment
        from apps.payments.services import cancel_cash_movements_of

        if not pagamento_integral:
            # Recebimentos parciais precisam sair do caixa ao cancelar a venda.
            for payment in order.payments.select_for_update().filter(
                status__in=[Payment.STATUS_PENDING, Payment.STATUS_APPROVED]
            ).order_by("pk"):
                payment.status = Payment.STATUS_CANCELLED
                payment.updated_by = user
                payment.save(update_fields=["status", "updated_by", "updated_at"])
                cancel_cash_movements_of(payment, user=user)
                record_audit(
                    action=AuditLog.ACTION_CANCELLED,
                    instance=payment,
                    actor=user,
                    reason=reason,
                    metadata={"order": str(order.id), "event": "payment_cancelled"},
                )
        # Não retire itens da origem enquanto o caixa monta a conta.
        now = timezone.now()
        if not authorization:
            authorization = Order.AUTHORIZATION_DELEGATED if authorized_by is not None else Order.AUTHORIZATION_OWN
        order.status = Order.STATUS_CANCELLED
        order.payment_status = Order.PAYMENT_REFUNDED if pagamento_integral else Order.PAYMENT_CANCELLED
        order.cancel_reason = reason
        order.cancelled_at = now
        order.cancelled_by = user
        order.cancel_authorized_by = authorized_by
        order.cancel_authorization = authorization
        order.updated_by = user
        order.save(
            update_fields=[
                "status",
                "payment_status",
                "cancel_reason",
                "cancelled_at",
                "cancelled_by",
                "cancel_authorized_by",
                "cancel_authorization",
                "updated_by",
                "updated_at",
            ]
        )
        order.items.exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED]).update(
            status=OrderItem.STATUS_CANCELLED, void_reason=reason, voided_at=now, voided_by=user
        )
        # O CUPOM VOLTA A VALER. Uma venda cancelada nao consumiu o direito do
        # cliente, e deixar o resgate gravado transformaria um cancelamento por
        # erro de digitacao na perda definitiva de um cupom de compra unica.
        from apps.promotions.coupon_service import devolver_resgate

        devolver_resgate(order)
        # Conta cancelada: as anotações saem como PERDA, não como venda. É a
        # distinção que o fechamento do mês precisa, e que um estado só apagaria.
        conclude_items_of_order(order, when=now, billed=False)
        if order.table_id:
            free_table_if_empty(order.table)
        free_command_for_order(order)
        record_audit(
            action=AuditLog.ACTION_CANCELLED,
            instance=order,
            actor=user,
            reason=reason,
            # QUEM PEDIU e QUEM LIBEROU. Sem o segundo, o registro dizia apenas
            # que o operador cancelou — e a pergunta que a auditoria existe
            # para responder ("quem autorizou isso?") ficava sem resposta
            # justamente no caso em que ela importa: o operador nao tinha a
            # permissao e alguem a emprestou para aquela operacao.
            metadata={
                "event": "order_cancelled",
                "requested_by": str(getattr(user, "id", "") or ""),
                "requested_by_username": getattr(user, "username", "") or "",
                "authorized_by": str(getattr(authorized_by, "id", "") or ""),
                "authorized_by_username": getattr(authorized_by, "username", "") or "",
                "authorization": authorization,
            },
        )
        return order


def sync_production_status(order):
    """Recalculate order.production_status based on active item statuses."""
    with tenant_context(order.account):
        order = Order.objects.get(pk=order.pk)
        active_statuses = list(
            order.items.exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED]).values_list(
                "status", flat=True
            )
        )
        if not active_statuses:
            return order

        if all(s == OrderItem.STATUS_DELIVERED for s in active_statuses):
            order.production_status = Order.PROD_DELIVERED
        elif all(s == OrderItem.STATUS_READY for s in active_statuses):
            order.production_status = Order.PROD_READY
        elif any(s == OrderItem.STATUS_READY for s in active_statuses):
            order.production_status = Order.PROD_PARTIALLY_READY
        elif any(s == OrderItem.STATUS_PREPARING for s in active_statuses):
            order.production_status = Order.PROD_PREPARING
        elif any(s in {OrderItem.STATUS_SENT, OrderItem.STATUS_PREPARING} for s in active_statuses):
            order.production_status = Order.PROD_SENT

        order.save(update_fields=["production_status", "updated_at"])
        return order


def serialize_kitchen_item(item):
    """O item como a cozinha o enxerga, com a ORIGEM dele, nao com o destino.

    Depois de uma consolidacao `item.order` e o pedido final — cuja comanda e
    uma so, ou nenhuma. Ler a comanda dali faria o card do KDS mostrar a
    comanda errada: item de quatro pessoas diferentes apareceria como sendo de
    uma. O item guarda a propria comanda desde o lancamento, e e ela que manda.
    """
    order = item.order
    command = item.command or order.command
    return {
        "id": str(item.id),
        "account_id": str(item.account_id),
        # O pedido ATUAL e o que a tela de pagamento conhece; o de producao e o
        # que a cozinha imprimiu. Os dois viajam para ninguem ter de adivinhar.
        "order_id": str(item.order_id),
        "production_order_id": str(order.id),
        "order_sequence": order.sequence,
        "order_type": order.order_type,
        "table": order.table.number if order.table_id else None,
        "command": command.code if command else None,
        "customer": order.customer.name if order.customer_id else None,
        "product": item.product.name,
        "quantity": str(item.quantity),
        "note": item.customer_note,
        "variations": item.variations,
        "status": item.status,
        "production_sector": item.production_sector,
        "batch_number": item.batch.batch_number if item.batch_id else None,
        "sent_to_kitchen_at": item.sent_to_kitchen_at.isoformat() if item.sent_to_kitchen_at else None,
        "elapsed_from": item.sent_to_kitchen_at.isoformat()
        if item.sent_to_kitchen_at
        else item.launched_at.isoformat(),
    }
