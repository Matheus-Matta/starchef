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
def create_order(*, restaurant, order_type, user, branch=None, **kwargs):
    account = restaurant.account

    with tenant_context(account):
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

        order = Order.objects.create(
            account=account,
            restaurant=restaurant,
            branch=None,
            sequence=next_order_sequence(restaurant),
            order_type=order_type,
            responsible_user=user,
            created_by=user,
            updated_by=user,
            **kwargs,
        )

        if order.table_id:
            order.table.status = Table.STATUS_OCCUPIED
            order.table.current_order_id = order.id
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
    command.status = Command.STATUS_FREE
    command.current_order_id = None
    command.customer_name = ""
    command.save(update_fields=["status", "current_order_id", "customer_name", "updated_at"])


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

        existing = None
        if not product.is_weighed:
            candidates = OrderItem.objects.select_for_update().filter(
                order=order, product=product, status=OrderItem.STATUS_PENDING,
                customer_note=customer_note, variations=variation_snapshot,
            ).prefetch_related("addons")
            selected_addon_ids = {str(a.id) for a in selected_addons}
            existing = next((candidate for candidate in candidates if {
                str(a.addon_id) for a in candidate.addons.all()
            } == selected_addon_ids), None)
        if existing is not None:
            existing.quantity += quantity
            existing.unit_price = unit_price
            existing.total_price = (unit_price * existing.quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            existing.updated_by = user
            existing.save(update_fields=["quantity", "unit_price", "total_price", "updated_by", "updated_at"])
            for item_addon in existing.addons.all():
                item_addon.total_price = (item_addon.unit_price * existing.quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
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
                account=order.account, restaurant=order.restaurant, branch=order.branch,
                item=item, addon=addon, quantity=1, unit_price=addon.price,
                total_price=addon.price * quantity, created_by=user, updated_by=user,
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
def send_order_to_kitchen(order, user):
    with tenant_context(order.account):
        order = Order.objects.select_for_update().prefetch_related("items__product").get(pk=order.pk)
        if order.is_locked:
            raise ValidationError("Pedidos bloqueados não podem ser enviados para a cozinha.")

        items = list(order.items.filter(status=OrderItem.STATUS_PENDING))
        if not items:
            raise ValidationError("Não há itens pendentes para enviar à cozinha.")

        now = timezone.now()

        # Each send creates a new production round
        last_batch_number = order.batches.aggregate(value=Max("batch_number"))["value"] or 0
        batch = OrderBatch.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            order=order,
            batch_number=last_batch_number + 1,
            status=OrderBatch.STATUS_SENT,
            sent_at=now,
            sent_by=user,
            created_by=user,
            updated_by=user,
        )

        for item in items:
            item.status = OrderItem.STATUS_SENT
            item.batch = batch
            item.sent_to_kitchen_at = now
            item.updated_by = user
            item.save(update_fields=["status", "batch", "sent_to_kitchen_at", "updated_by", "updated_at"])
            broadcast_kitchen_event(
                order.account_id,
                order.branch_id,
                item.production_sector,
                "order_item.sent",
                serialize_kitchen_item(item),
            )

        order.production_status = Order.PROD_SENT
        order.updated_by = user
        order.save(update_fields=["production_status", "updated_by", "updated_at"])
        record_audit(action=AuditLog.ACTION_UPDATED, instance=order, actor=user, metadata={"event": "send_to_kitchen", "batch": batch.batch_number})

        from apps.printers.services import register_kitchen_batch_print_jobs

        register_kitchen_batch_print_jobs(batch=batch, user=user)

        if order.restaurant.stock_deduction_timing == "kitchen":
            from apps.stock.services import deduct_order_stock

            deduct_order_stock(order=order, user=user)

        return order


@transaction.atomic
def void_order_item(item, user, reason=""):
    """Cancel a pending item before it is sent to kitchen."""
    if not reason.strip():
        raise ValidationError("Informe o motivo do cancelamento do item.")
    with tenant_context(item.account):
        item = OrderItem.objects.select_for_update().select_related("order").get(pk=item.pk)
        if item.order.is_locked:
            raise ValidationError("Itens de pedidos pagos, cancelados ou estornados não podem ser alterados.")
        if item.status != OrderItem.STATUS_PENDING:
            raise ValidationError("Somente itens pendentes podem ser cancelados. Para itens já enviados, use cortesia.")
        item.status = OrderItem.STATUS_CANCELLED
        item.void_reason = reason
        item.updated_by = user
        item.save(update_fields=["status", "void_reason", "updated_by", "updated_at"])
        recalculate_order(item.order)
        record_audit(action=AuditLog.ACTION_CANCELLED, instance=item, actor=user, reason=reason)
        return item


@transaction.atomic
def comp_order_item(item, user, reason=""):
    """Mark a sent/in-production item as comped (courtesy) — does not deduct from bill."""
    with tenant_context(item.account):
        item = OrderItem.objects.select_for_update().select_related("order").get(pk=item.pk)
        if item.order.is_locked:
            raise ValidationError("Itens de pedidos pagos, cancelados ou estornados não podem ser alterados.")
        if item.status in {OrderItem.STATUS_PENDING, OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED}:
            raise ValidationError("A cortesia só pode ser aplicada a itens já enviados à cozinha. Cancele itens que ainda estão pendentes.")

        profile = getattr(user, "profile", None)
        if not profile or profile.profile_type not in {"admin", "owner", "manager"}:
            raise ValidationError("Aplicar cortesia exige permissão de gerente.")

        item.status = OrderItem.STATUS_COMPED
        item.void_reason = reason
        item.updated_by = user
        item.save(update_fields=["status", "void_reason", "updated_by", "updated_at"])
        recalculate_order(item.order)
        record_audit(action=AuditLog.ACTION_UPDATED, instance=item, actor=user, reason=reason, metadata={"event": "comp"})
        return item


@transaction.atomic
def update_order_item_status(item, new_status, user, reason=""):
    with tenant_context(item.account):
        item = OrderItem.objects.select_for_update().select_related("order").get(pk=item.pk)
        if item.order.is_locked:
            raise ValidationError("Itens de pedidos pagos, cancelados ou estornados não podem ser alterados.")

        # Guard special transitions through dedicated functions
        if new_status == OrderItem.STATUS_CANCELLED:
            return void_order_item(item, user, reason)
        if new_status == OrderItem.STATUS_COMPED:
            return comp_order_item(item, user, reason)

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
        record_audit(action=AuditLog.ACTION_UPDATED, instance=item, actor=user, reason=reason, metadata={"status": new_status})
        broadcast_kitchen_event(
            item.account_id,
            item.branch_id,
            item.production_sector,
            "order_item.status_changed",
            serialize_kitchen_item(item),
        )
        return item


@transaction.atomic
def close_order(order, user, *, discount=Decimal("0.00"), service_fee=None):
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
        if service_fee is not None:
            order.service_fee = Decimal(str(service_fee))
        elif order.restaurant.default_service_fee_percent:
            order.service_fee = (order.subtotal * order.restaurant.default_service_fee_percent) / Decimal("100")
        order.status = Order.STATUS_AWAITING_PAYMENT
        order.closed_by = user
        order.updated_by = user
        order.closed_at = timezone.now()
        order.save(update_fields=["discount", "service_fee", "status", "closed_by", "closed_at", "updated_by", "updated_at"])
        order = recalculate_order(order)
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
            order.table.status = Table.STATUS_FREE
            order.table.current_order_id = None
            order.table.save(update_fields=["status", "current_order_id", "updated_at"])
        free_command_for_order(order)
        record_audit(action=AuditLog.ACTION_CANCELLED, instance=order, actor=user, reason=reason)
        return order


def sync_production_status(order):
    """Recalculate order.production_status based on active item statuses."""
    with tenant_context(order.account):
        order = Order.objects.get(pk=order.pk)
        active_statuses = list(
            order.items.exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED]).values_list("status", flat=True)
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
        "elapsed_from": item.sent_to_kitchen_at.isoformat() if item.sent_to_kitchen_at else item.launched_at.isoformat(),
    }
