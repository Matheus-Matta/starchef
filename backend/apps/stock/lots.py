"""Entradas, lotes e saidas manuais — o estoque por lote.

O que separa este modulo de `services.py`: ali o consumo vem de uma venda e o
sistema decide sozinho; aqui um operador digita, confere e confirma. Por isso
tudo nasce como rascunho e so vira movimento na confirmacao.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.menu.units import IncompatibleUnitError, convert
from apps.stock.models import (
    StockAllocation,
    StockEntry,
    StockExit,
    StockLot,
    StockMovement,
    StockSettings,
)

QUANTITY_PLACES = Decimal("0.001")
MONEY_PLACES = Decimal("0.01")


def settings_for(account):
    """A configuracao da conta, ou os padroes quando ela ainda nao existe.

    Nao cria a linha: uma conta que nunca abriu a tela de configuracao deve
    operar com os padroes recomendados (FEFO, bloqueia vencido, nao permite
    negativo) em vez de falhar.
    """
    existing = StockSettings.objects.filter(account=account).first()
    if existing:
        return existing
    return StockSettings(account=account)


def base_quantity_for(item):
    """Quantidade da linha de entrada na unidade base do insumo."""
    packages = Decimal(str(item.package_quantity or 0))
    content = Decimal(str(item.content_per_package or 0))
    total = packages * content
    unit = item.content_unit or item.ingredient.unit
    try:
        return convert(total, unit, item.ingredient.unit)
    except IncompatibleUnitError as error:
        raise ValidationError({"content_unit": str(error)}) from None


# ── entrada ─────────────────────────────────────────────────────────────────
@transaction.atomic
def post_stock_entry(*, entry, user):
    """Confirma a entrada: cria os lotes e os movimentos positivos."""
    with tenant_context(entry.account):
        entry = StockEntry.objects.select_for_update(of=("self",)).get(pk=entry.pk)
        if entry.status != StockEntry.STATUS_DRAFT:
            raise ValidationError("Somente uma entrada em rascunho pode ser confirmada.")

        items = list(entry.items.select_related("ingredient"))
        if not items:
            raise ValidationError("Adicione ao menos um insumo antes de confirmar a entrada.")

        config = settings_for(entry.account)
        lots = []
        for item in items:
            if config.expiry_control_enabled and not item.expires_at:
                raise ValidationError(
                    f"A validade e obrigatoria nesta filial: informe a validade de {item.ingredient.name}."
                )
            if item.expires_at and item.expires_at < entry.effective_date:
                raise ValidationError(
                    f"A validade de {item.ingredient.name} e anterior a data da entrada."
                )

            quantity = base_quantity_for(item).quantize(QUANTITY_PLACES)
            if quantity <= 0:
                raise ValidationError(f"A quantidade de {item.ingredient.name} deve ser maior que zero.")

            item.base_quantity = quantity
            item.total_cost = (quantity * Decimal(str(item.unit_cost or 0))).quantize(MONEY_PLACES)
            item.save(update_fields=["base_quantity", "total_cost", "updated_at"])

            lot = StockLot.objects.create(
                account=entry.account,
                restaurant=entry.restaurant,
                branch=entry.branch,
                ingredient=item.ingredient,
                location=entry.location,
                entry_item=item,
                code=StockLot.build_code(item.ingredient),
                supplier_lot=item.supplier_lot,
                entered_at=entry.effective_date,
                manufactured_at=item.manufactured_at,
                expires_at=item.expires_at,
                initial_quantity=quantity,
                quantity=quantity,
                unit_cost=item.unit_cost or 0,
                created_by=user,
                updated_by=user,
            )
            lots.append(lot)

            StockMovement.objects.create(
                account=entry.account,
                restaurant=entry.restaurant,
                branch=entry.branch,
                ingredient=item.ingredient,
                location=entry.location,
                lot=lot,
                entry=entry,
                operator=user,
                movement_type=StockMovement.TYPE_IN,
                quantity=quantity,
                unit_cost=item.unit_cost or 0,
                total_cost=item.total_cost,
                reason=f"Entrada {entry.document_number or entry.id}",
                source_key=f"entry:{entry.id}:item:{item.id}",
                created_by=user,
                updated_by=user,
            )

            if item.unit_cost and item.unit_cost > 0:
                from apps.menu.services import update_ingredient_average_cost

                update_ingredient_average_cost(item.ingredient, quantity, item.unit_cost)

        entry.status = StockEntry.STATUS_POSTED
        entry.posted_at = timezone.now()
        entry.posted_by = user
        entry.updated_by = user
        entry.save(update_fields=["status", "posted_at", "posted_by", "updated_by", "updated_at"])
        record_audit(action=AuditLog.ACTION_UPDATED, instance=entry, actor=user, metadata={"event": "entry_posted"})
        return lots


@transaction.atomic
def cancel_stock_entry(*, entry, user, reason=""):
    """Cancela uma entrada. Confirmada, exige que os lotes estejam intactos."""
    with tenant_context(entry.account):
        entry = StockEntry.objects.select_for_update(of=("self",)).get(pk=entry.pk)
        if entry.status == StockEntry.STATUS_CANCELLED:
            raise ValidationError("Esta entrada ja esta cancelada.")

        if entry.status == StockEntry.STATUS_POSTED:
            lots = StockLot.objects.filter(entry_item__entry=entry).select_for_update(of=("self",))
            consumed = [lot for lot in lots if lot.quantity != lot.initial_quantity]
            if consumed:
                # Cancelar devolveria um saldo que ja saiu — o numero ficaria
                # negativo ou, pior, plausivel e errado.
                nomes = ", ".join(lot.code for lot in consumed[:5])
                raise ValidationError(
                    f"Lotes ja consumidos ({nomes}). Faca um ajuste justificado em vez de cancelar a entrada."
                )
            for lot in lots:
                StockMovement.objects.create(
                    account=entry.account,
                    restaurant=entry.restaurant,
                    branch=entry.branch,
                    ingredient=lot.ingredient,
                    location=lot.location,
                    lot=lot,
                    entry=entry,
                    operator=user,
                    movement_type=StockMovement.TYPE_REVERSAL,
                    quantity=-lot.quantity,
                    unit_cost=lot.unit_cost,
                    total_cost=-(lot.quantity * lot.unit_cost).quantize(MONEY_PLACES),
                    reason=reason or f"Cancelamento da entrada {entry.document_number or entry.id}",
                    source_key=f"entry-cancel:{entry.id}:lot:{lot.id}",
                    created_by=user,
                    updated_by=user,
                )
                lot.quantity = Decimal("0")
                lot.status = StockLot.STATUS_DISCARDED
                lot.updated_by = user
                lot.save(update_fields=["quantity", "status", "updated_by", "updated_at"])

        entry.status = StockEntry.STATUS_CANCELLED
        entry.cancelled_at = timezone.now()
        entry.cancelled_by = user
        entry.updated_by = user
        entry.save(update_fields=["status", "cancelled_at", "cancelled_by", "updated_by", "updated_at"])
        record_audit(action=AuditLog.ACTION_CANCELLED, instance=entry, actor=user, reason=reason)
        return entry


# ── separacao FIFO / FEFO ───────────────────────────────────────────────────
def pickable_lots(*, ingredient, location, strategy, block_expired=True, today=None):
    """Lotes candidatos, na ordem em que devem ser consumidos.

    Bloqueado, esgotado, vencido e descartado ficam de fora. No FEFO, lote SEM
    validade vai para o fim: ele nao tem urgencia declarada, e coloca-lo antes
    de um lote que vence amanha e exatamente o que o FEFO existe para evitar.
    """
    today = today or timezone.localdate()
    queryset = StockLot.objects.filter(
        ingredient=ingredient,
        location=location,
        status=StockLot.STATUS_AVAILABLE,
        quantity__gt=0,
    )
    if block_expired:
        queryset = queryset.exclude(expires_at__lt=today)

    lots = list(queryset)
    if strategy == StockSettings.PICKING_FEFO:
        lots.sort(key=lambda lot: (lot.expires_at is None, lot.expires_at or today, lot.entered_at, str(lot.id)))
    else:
        lots.sort(key=lambda lot: (lot.entered_at, lot.created_at, str(lot.id)))
    return lots


@transaction.atomic
def suggest_exit_lots(*, exit_document, user):
    """Refaz a sugestao de lotes de toda a saida, respeitando FIFO/FEFO."""
    with tenant_context(exit_document.account):
        if exit_document.status != StockExit.STATUS_DRAFT:
            raise ValidationError("Somente uma saida em rascunho pode ser re-separada.")

        config = settings_for(exit_document.account)
        strategy = config.picking_strategy
        exit_document.picking_strategy = strategy
        exit_document.require_label_scan = (
            exit_document.require_label_scan or config.require_label_scan_on_manual_exit
        )
        exit_document.updated_by = user
        exit_document.save(
            update_fields=["picking_strategy", "require_label_scan", "updated_by", "updated_at"]
        )

        shortages = []
        for item in exit_document.items.select_related("ingredient"):
            # Re-separar descarta a sugestao anterior: as conferencias feitas
            # apontavam para lotes que podem nao ser mais os indicados.
            item.allocations.all().delete()

            remaining = Decimal(str(item.requested_quantity))
            lots = pickable_lots(
                ingredient=item.ingredient,
                location=exit_document.location,
                strategy=strategy,
                block_expired=config.block_expired_stock,
            )
            for lot in lots:
                if remaining <= 0:
                    break
                take = min(remaining, lot.quantity)
                if take <= 0:
                    continue
                StockAllocation.objects.create(
                    account=exit_document.account,
                    restaurant=exit_document.restaurant,
                    branch=exit_document.branch,
                    exit_item=item,
                    lot=lot,
                    suggested_quantity=take.quantize(QUANTITY_PLACES),
                    confirmed_quantity=take.quantize(QUANTITY_PLACES),
                    created_by=user,
                    updated_by=user,
                )
                remaining -= take

            item.fulfilled_quantity = (Decimal(str(item.requested_quantity)) - remaining).quantize(QUANTITY_PLACES)
            item.save(update_fields=["fulfilled_quantity", "updated_at"])
            if remaining > 0:
                shortages.append(
                    {
                        "ingredient": str(item.ingredient.id),
                        "ingredient_name": item.ingredient.name,
                        "missing": str(remaining.quantize(QUANTITY_PLACES)),
                    }
                )
        return shortages


@transaction.atomic
def scan_exit_label(*, exit_document, code, user, quantity=None):
    """Confere uma etiqueta lida contra os lotes indicados para esta saida."""
    with tenant_context(exit_document.account):
        if exit_document.status != StockExit.STATUS_DRAFT:
            raise ValidationError("Esta saida ja foi confirmada.")

        normalized = str(code or "").strip().upper()
        if not normalized:
            raise ValidationError({"code": "Leia ou digite o codigo da etiqueta."})

        lot = StockLot.objects.filter(code=normalized).first()
        if lot is None:
            raise ValidationError({"code": f"Nenhum lote encontrado para a etiqueta {normalized}."})

        allocation = (
            StockAllocation.objects.filter(exit_item__exit=exit_document, lot=lot)
            .select_related("lot", "exit_item__ingredient")
            .first()
        )
        if allocation is None:
            # A mensagem precisa dizer QUAL lote era para sair: sem isso o
            # operador so sabe que errou, nao o que fazer em seguida.
            expected = (
                StockAllocation.objects.filter(
                    exit_item__exit=exit_document, exit_item__ingredient=lot.ingredient
                )
                .select_related("lot")
                .first()
            )
            if expected is not None:
                raise ValidationError(
                    {
                        "code": (
                            f"A etiqueta {normalized} nao e o lote indicado para {lot.ingredient.name}. "
                            f"Retire o lote {expected.lot.code}"
                            + (f" (vence em {expected.lot.expires_at:%d/%m/%Y})" if expected.lot.expires_at else "")
                            + "."
                        )
                    }
                )
            raise ValidationError(
                {"code": f"A etiqueta {normalized} e de {lot.ingredient.name}, que nao esta nesta saida."}
            )

        if allocation.lot.location_id != exit_document.location_id:
            raise ValidationError({"code": f"O lote {normalized} pertence a outro local de estoque."})
        if allocation.scanned_at:
            raise ValidationError({"code": f"A etiqueta {normalized} ja foi conferida."})

        if quantity is not None:
            confirmed = Decimal(str(quantity))
            if confirmed <= 0 or confirmed > allocation.lot.quantity:
                raise ValidationError({"quantity": "Quantidade invalida para este lote."})
            allocation.confirmed_quantity = confirmed.quantize(QUANTITY_PLACES)

        allocation.scanned_code = normalized
        allocation.scanned_at = timezone.now()
        allocation.scanned_by = user
        allocation.updated_by = user
        allocation.save(
            update_fields=[
                "scanned_code", "scanned_at", "scanned_by", "confirmed_quantity", "updated_by", "updated_at"
            ]
        )
        return allocation


@transaction.atomic
def post_stock_exit(*, exit_document, user):
    """Confirma a saida: gera os movimentos negativos e baixa os lotes."""
    with tenant_context(exit_document.account):
        exit_document = StockExit.objects.select_for_update(of=("self",)).get(pk=exit_document.pk)
        if exit_document.status != StockExit.STATUS_DRAFT:
            raise ValidationError("Somente uma saida em rascunho pode ser confirmada.")

        config = settings_for(exit_document.account)
        items = list(exit_document.items.select_related("ingredient").prefetch_related("allocations__lot"))
        if not items:
            raise ValidationError("Adicione ao menos um insumo antes de confirmar a saida.")

        movements = []
        for item in items:
            allocations = list(item.allocations.all())
            if not allocations:
                raise ValidationError(
                    f"Separe os lotes de {item.ingredient.name} antes de confirmar a saida."
                )

            total = sum((Decimal(str(a.confirmed_quantity)) for a in allocations), Decimal("0"))
            if not config.allow_negative_stock and total < Decimal(str(item.requested_quantity)):
                raise ValidationError(
                    f"Saldo insuficiente de {item.ingredient.name}: "
                    f"pedido {item.requested_quantity}, separado {total}."
                )

            for allocation in allocations:
                if exit_document.require_label_scan and not allocation.scanned_at:
                    raise ValidationError(
                        f"Confira a etiqueta do lote {allocation.lot.code} antes de confirmar."
                    )

                lot = StockLot.objects.select_for_update(of=("self",)).get(pk=allocation.lot_id)
                quantity = Decimal(str(allocation.confirmed_quantity))
                if quantity <= 0:
                    continue
                if quantity > lot.quantity and not config.allow_negative_stock:
                    raise ValidationError(
                        f"O lote {lot.code} tem {lot.quantity} disponivel, menos que os {quantity} separados."
                    )

                movements.append(
                    StockMovement.objects.create(
                        account=exit_document.account,
                        restaurant=exit_document.restaurant,
                        branch=exit_document.branch,
                        ingredient=item.ingredient,
                        location=exit_document.location,
                        lot=lot,
                        exit=exit_document,
                        operator=user,
                        movement_type=StockMovement.TYPE_OUT,
                        quantity=-quantity,
                        unit_cost=lot.unit_cost,
                        total_cost=-(quantity * lot.unit_cost).quantize(MONEY_PLACES),
                        reason=exit_document.reason,
                        source_key=f"exit:{exit_document.id}:allocation:{allocation.id}",
                        created_by=user,
                        updated_by=user,
                    )
                )

                lot.quantity = (lot.quantity - quantity).quantize(QUANTITY_PLACES)
                if lot.quantity <= 0:
                    lot.status = StockLot.STATUS_DEPLETED
                lot.updated_by = user
                lot.save(update_fields=["quantity", "status", "updated_by", "updated_at"])

            item.fulfilled_quantity = total.quantize(QUANTITY_PLACES)
            item.save(update_fields=["fulfilled_quantity", "updated_at"])

        exit_document.status = StockExit.STATUS_POSTED
        exit_document.posted_at = timezone.now()
        exit_document.posted_by = user
        exit_document.updated_by = user
        exit_document.save(
            update_fields=["status", "posted_at", "posted_by", "updated_by", "updated_at"]
        )
        record_audit(
            action=AuditLog.ACTION_UPDATED, instance=exit_document, actor=user, metadata={"event": "exit_posted"}
        )
        return movements
