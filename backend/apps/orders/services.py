import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.orders.events import broadcast_kitchen_event
from apps.menu.models import ProductVariation
from apps.orders.models import Order, OrderBatch, OrderItem, OrderItemAddon
from apps.restaurants.models import Command, Table

TWO_PLACES = Decimal("0.01")
THREE_PLACES = Decimal("0.001")


def next_order_sequence(restaurant):
    with tenant_context(restaurant.account):
        last_sequence = Order.objects.filter(restaurant=restaurant).aggregate(value=Max("sequence"))["value"] or 0
        return last_sequence + 1


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
            if command.status == Command.STATUS_OCCUPIED:
                raise ValidationError("A comanda já está em uso.")
            kwargs["command"] = command
            # A mesa é um vínculo da comanda. O pedido guarda apenas o snapshot
            # para histórico, relatórios e impressão após o pagamento.
            kwargs["table"] = command.current_table

        order = Order.objects.create(
            account=account,
            restaurant=restaurant,
            branch=None,
            sequence=next_order_sequence(restaurant),
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
            command.status = Command.STATUS_OCCUPIED
            command.current_order_id = order.id
            if order.customer_id and not command.customer_name:
                command.customer_name = order.customer.name
            command.save(update_fields=["status", "current_order_id", "customer_name", "updated_at"])

        record_audit(action=AuditLog.ACTION_CREATED, instance=order, actor=user)
        return order


def free_command_for_order(order):
    """Zera e libera a comanda vinculada ao pedido (reuso). No-op se sem comanda.

    Espelha a liberação da mesa; chamado no pagamento total e no cancelamento.
    Assume estar dentro de transação/tenant_context do chamador.
    """
    if not order.command_id:
        return
    command = Command.objects.select_for_update().get(pk=order.command_id)
    old_table_id = command.current_table_id

    command.status = Command.STATUS_FREE
    command.current_order_id = None
    command.customer_name = ""
    command.current_table = None
    command.save(update_fields=["status", "current_order_id", "customer_name", "current_table", "updated_at"])

    if old_table_id:
        from apps.restaurants.models import CommandMovementLog, Table

        CommandMovementLog.objects.create(
            account=command.account,
            restaurant=command.restaurant,
            branch=command.branch,
            command=command,
            action=CommandMovementLog.ACTION_UNLINKED,
            from_table_id=old_table_id,
            waiter=order.updated_by,
        )

        # A ocupação da mesa é determinada exclusivamente pelas comandas
        # vinculadas. O pedido mantém `table` apenas como histórico.
        table = Table.objects.select_for_update().get(pk=old_table_id)
        active_commands = table.active_commands.exists()

        if not active_commands:
            table.status = Table.STATUS_FREE
            table.current_order_id = None
            table.save(update_fields=["status", "current_order_id", "updated_at"])


def free_table_if_empty(table):
    """Libera a mesa quando nenhuma comanda está vinculada a ela."""
    if not table:
        return
    table = Table.objects.select_for_update().get(pk=table.pk)
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
        weight_kg = Decimal(str(weight_kg)).quantize(THREE_PLACES)
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
):
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        if product.account_id != order.account_id:
            raise ValidationError("O produto não pertence à conta do pedido.")
        if not product.restaurants.filter(pk=order.restaurant_id).exists():
            raise ValidationError("O produto não está disponível neste restaurante.")
        if order.is_locked:
            raise ValidationError("Pedidos pagos, cancelados ou estornados não podem ser alterados.")
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
            quantity = Decimal(str(quantity if quantity is not None else 1))
            if quantity <= 0:
                raise ValidationError("Quantidade deve ser maior que zero.")

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
            expected = Decimal(str(expected_unit_price)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
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
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        excluded = {OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED}
        subtotal = order.items.exclude(status__in=excluded).aggregate(value=Sum("total_price"))["value"]
        order.subtotal = subtotal or Decimal("0.00")
        order.total = order.subtotal + order.service_fee + order.delivery_fee - order.discount
        if order.total < Decimal("0.00"):
            order.total = Decimal("0.00")
        order.save(update_fields=["subtotal", "total", "updated_at"])
        return order


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
        dispatch_at = now

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
                "immediate": True,
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
                free_table_if_empty(Table.objects.get(pk=old_table_id))

        order = create_order(
            restaurant=restaurant,
            order_type=order_type,
            command=command,
            user=user,
            responsible_user=responsible_user,
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

        from apps.printers.models import PrintJob

        PrintJob.objects.filter(
            payload__batch_id=str(batch.id),
            status=PrintJob.STATUS_SCHEDULED,
        ).update(status=PrintJob.STATUS_RENDERED, available_at=now, updated_at=now)

        if order.restaurant.stock_deduction_timing == "kitchen":
            from apps.stock.services import deduct_order_stock

            deduct_order_stock(order=order, user=batch.sent_by)

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
    quantity = Decimal(str(quantity))
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


def void_order_item(item, user, reason="", offline_printed=False):
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

        was_dispatched = item.status not in {OrderItem.STATUS_PENDING, OrderItem.STATUS_QUEUED}
        item.status = OrderItem.STATUS_CANCELLED
        item.void_reason = reason
        item.updated_by = user
        item.save(update_fields=["status", "void_reason", "updated_by", "updated_at"])
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

        profile = getattr(user, "profile", None)
        if not profile or profile.profile_type not in {"admin", "owner", "manager"}:
            raise ValidationError("Aplicar cortesia exige permissão de gerente.")

        item.status = OrderItem.STATUS_COMPED
        item.void_reason = reason
        item.updated_by = user
        item.save(update_fields=["status", "void_reason", "updated_by", "updated_at"])
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
            profile = getattr(user, "profile", None)
            if not profile or profile.profile_type not in {"admin", "owner", "manager"}:
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
    expected_total=None,
):
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.is_locked:
            raise ValidationError("Pedidos bloqueados não podem ser fechados.")
        # O valor pode chegar como str/float/int (corpo da requisição) — normaliza
        # para Decimal antes de comparar/gravar.
        discount = Decimal(str(discount or 0))
        if discount > Decimal("0.00"):
            profile = getattr(user, "profile", None)
            if not profile or profile.profile_type not in {"admin", "owner", "manager"}:
                raise ValidationError("Aplicar desconto exige permissão de gerente.")

        order.discount = discount
        if service_fee_enabled is not None:
            if isinstance(service_fee_enabled, str):
                service_fee_enabled = service_fee_enabled.lower() in {"1", "true", "yes", "on"}
            order.service_fee_enabled = bool(service_fee_enabled)
        if not order.service_fee_enabled:
            order.service_fee = Decimal("0.00")
        elif service_fee is not None:
            order.service_fee = Decimal(str(service_fee)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        elif order.restaurant.default_service_fee_percent:
            # Arredonda aqui, e não deixa para o campo do banco: SQLite não trunca
            # DecimalField como o Postgres, então o total recalculado a seguir
            # divergia do total previsto pelo cliente (que já soma a taxa
            # arredondada), derrubando o fechamento por "total mudou offline".
            order.service_fee = (
                (order.subtotal * order.restaurant.default_service_fee_percent) / Decimal("100")
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        order.status = Order.STATUS_AWAITING_PAYMENT
        order.closed_by = user
        order.updated_by = user
        order.closed_at = timezone.now()
        order.save(
            update_fields=[
                "discount",
                "service_fee",
                "service_fee_enabled",
                "status",
                "closed_by",
                "closed_at",
                "updated_by",
            ]
        )
        order = recalculate_order(order)
        if expected_total not in (None, ""):
            expected = Decimal(str(expected_total)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if expected != order.total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP):
                raise ValidationError(
                    "O total do pedido mudou durante o período offline. "
                    "Revise os valores antes de registrar o pagamento."
                )

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
            if order.table_id:
                free_table_if_empty(order.table)
            free_command_for_order(order)
            if order.restaurant.stock_deduction_timing == "payment":
                from apps.stock.services import deduct_order_stock

                deduct_order_stock(order=order, user=user)
        record_audit(action=AuditLog.ACTION_UPDATED, instance=order, actor=user, metadata={"event": "close_order"})
        return order


@transaction.atomic
def cancel_order(order, user, reason):
    if not reason:
        raise ValidationError("O motivo do cancelamento é obrigatório.")
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == Order.STATUS_PAID:
            raise ValidationError("Pedidos pagos devem ser estornados, não cancelados.")
        order.status = Order.STATUS_CANCELLED
        order.cancel_reason = reason
        order.updated_by = user
        order.save(update_fields=["status", "cancel_reason", "updated_by", "updated_at"])
        order.items.exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED]).update(
            status=OrderItem.STATUS_CANCELLED, void_reason=reason
        )
        if order.table_id:
            free_table_if_empty(order.table)
        free_command_for_order(order)
        record_audit(action=AuditLog.ACTION_CANCELLED, instance=order, actor=user, reason=reason)
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
    order = item.order
    return {
        "id": str(item.id),
        "account_id": str(item.account_id),
        "order_id": str(order.id),
        "order_sequence": order.sequence,
        "order_type": order.order_type,
        "table": order.table.number if order.table_id else None,
        "command": order.command.code if order.command_id else None,
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
