"""
Serviço de cancelamento e reconciliação de NF-e de entrada.
Garante que notas canceladas na SEFAZ não gerem estoque indevido,
preservando integridade contábil, histórico e auditoria.
"""

from decimal import Decimal
from typing import Optional, Dict, Any
from django.db import transaction, models
from django.utils import timezone

from apps.inbound_nfe.models import InboundNFe, NFeEvent, NFeIssue
from apps.stock.models import (
    GoodsReceipt,
    InventoryLot,
    StockMovement,
)
from apps.assets.models import Asset


@transaction.atomic
def apply_cancellation(
    invoice: InboundNFe,
    event: Optional[NFeEvent] = None,
    protocol: Optional[str] = None,
    reason: Optional[str] = None,
    event_datetime: Optional[timezone.datetime] = None,
    nsu: Optional[str] = None,
    actor=None,
) -> Dict[str, Any]:
    """
    Aplica o cancelamento a uma NF-e de entrada de forma idempotente e segura.

    Efeitos:
    1. Marca fiscal_status = CANCELLED e preenche metadados SEFAZ de cancelamento.
    2. Se a nota já gerou recebimento / estoque:
       - Cancela os registros de GoodsReceipt vinculados.
       - Marca os bens patrimoniais (Asset) como source_nfe_cancelled = True e abre NFeIssue.
       - Cancela lotes de estoque (InventoryLot).
       - Estorna movimentos de entrada (StockMovement) via lançamento compensatório
         TYPE_NFE_CANCELLATION_REVERSAL (reversal_of = entry_movement).
       - Se o saldo em estoque for inferior à quantidade de entrada (já houve consumo),
         abre NFeIssue(TYPE_CANCELLED_AFTER_STOCK_MOVEMENT) para o operador.
    3. Altera o status operacional da NF-e para CANCELLED se estava RECEIVED ou PENDING.
    """
    invoice_refreshed = InboundNFe.all_objects.select_for_update().get(id=invoice.id)

    cancellation_date = event_datetime or (event.event_datetime if event else None) or timezone.now()
    cancellation_protocol = protocol or (event.protocol if event else "") or invoice_refreshed.cancellation_protocol
    cancellation_reason = reason or (event.cancellation_reason if event else "") or invoice_refreshed.cancellation_reason
    cancellation_nsu = nsu or (event.nsu if event else "") or invoice_refreshed.cancellation_event_nsu

    result = {
        "invoice_id": str(invoice_refreshed.id),
        "access_key": invoice_refreshed.access_key,
        "fiscal_status": InboundNFe.FISCAL_CANCELLED,
        "already_cancelled": False,
        "receipts_cancelled": 0,
        "assets_flagged": 0,
        "lots_cancelled": 0,
        "reversals_created": 0,
        "issues_created": 0,
    }

    already_fiscal_cancelled = invoice_refreshed.fiscal_status == InboundNFe.FISCAL_CANCELLED

    # 1. Atualizar dados de cancelamento na NF-e
    invoice_refreshed.fiscal_status = InboundNFe.FISCAL_CANCELLED
    invoice_refreshed.cancelled_at = invoice_refreshed.cancelled_at or cancellation_date
    if cancellation_protocol:
        invoice_refreshed.cancellation_protocol = cancellation_protocol
    if cancellation_reason:
        invoice_refreshed.cancellation_reason = cancellation_reason
    if cancellation_nsu:
        invoice_refreshed.cancellation_event_nsu = cancellation_nsu

    # Se a nota estava pendente, ignorada ou recebida, muda status operacional para cancelada
    invoice_refreshed.status = InboundNFe.STATUS_CANCELLED

    invoice_refreshed.save(update_fields=[
        "fiscal_status",
        "cancelled_at",
        "cancellation_protocol",
        "cancellation_reason",
        "cancellation_event_nsu",
        "status",
        "updated_at",
    ])

    if already_fiscal_cancelled:
        result["already_cancelled"] = True
        # Continua para garantir que não restaram pendências ou movimentos sem reversão

    # 2. Cancelar GoodsReceipt vinculados
    receipts = GoodsReceipt.all_objects.filter(invoice=invoice_refreshed)
    for rcpt in receipts:
        if rcpt.status != GoodsReceipt.STATUS_CANCELLED:
            rcpt.status = GoodsReceipt.STATUS_CANCELLED
            cancel_note = f"\n[CANCELAMENTO SEFAZ] NF-e cancelada pelo emitente. Prot: {cancellation_protocol}."
            rcpt.notes = (rcpt.notes or "") + cancel_note
            rcpt.save(update_fields=["status", "notes", "updated_at"])
            result["receipts_cancelled"] += 1

    # 3. Tratar Ativos Patrimoniais (Asset)
    assets = Asset.all_objects.filter(nfe=invoice_refreshed)
    for asset in assets:
        flagged = False
        if not asset.source_nfe_cancelled:
            asset.source_nfe_cancelled = True
            flagged = True
        if event and not asset.source_nfe_cancellation_event:
            asset.source_nfe_cancellation_event = event
            flagged = True

        if flagged:
            asset.notes = (asset.notes or "") + f"\n[ALERTA] NF-e de origem {invoice_refreshed.number} foi cancelada na SEFAZ (Prot: {cancellation_protocol})."
            asset.save(update_fields=["source_nfe_cancelled", "source_nfe_cancellation_event", "notes", "updated_at"])
            result["assets_flagged"] += 1

        # Cria issue de pendência operacional para o bem
        issue_exists = NFeIssue.all_objects.filter(
            nfe=invoice_refreshed,
            issue_type=NFeIssue.TYPE_CANCELLED_AFTER_RECEIPT,
            description__contains=str(asset.id),
        ).exists()
        if not issue_exists:
            NFeIssue.objects.create(
                account=invoice_refreshed.account,
                restaurant=invoice_refreshed.restaurant,
                branch=invoice_refreshed.branch,
                nfe=invoice_refreshed,
                issue_type=NFeIssue.TYPE_CANCELLED_AFTER_RECEIPT,
                description=(
                    f"Bem patrimonial '{asset.product.name if asset.product else asset.asset_tag}' (ID {asset.id}) "
                    f"foi cadastrado a partir desta NF-e cancelada. O bem não foi deletado; "
                    f"verifique a destinação física ou vincule à nova NF-e substituta."
                ),
                created_by=actor,
            )
            result["issues_created"] += 1

    # 4. Tratar Lotes de Estoque (InventoryLot)
    lots = InventoryLot.all_objects.filter(nfe=invoice_refreshed)
    for lot in lots:
        if lot.status != InventoryLot.STATUS_CANCELLED:
            lot.status = InventoryLot.STATUS_CANCELLED
            lot.available_quantity = Decimal("0")
            lot.save(update_fields=["status", "available_quantity", "updated_at"])
            result["lots_cancelled"] += 1

    # 5. Estorno de Movimentos de Estoque (StockMovement)
    entry_movements = StockMovement.all_objects.filter(
        account=invoice_refreshed.account,
        nfe=invoice_refreshed,
        movement_type=StockMovement.TYPE_PURCHASE_ENTRY,
    )

    for entry_mov in entry_movements:
        # Verificar se já existe estorno para este movimento
        already_reversed = StockMovement.all_objects.filter(
            reversal_of=entry_mov,
            movement_type=StockMovement.TYPE_NFE_CANCELLATION_REVERSAL,
        ).exists()

        if already_reversed:
            continue

        item_product = entry_mov.product
        item_ingredient = entry_mov.ingredient

        # Calcular saldo atual do item no estoque
        current_balance = Decimal("0")
        if item_product:
            current_balance = (
                StockMovement.all_objects.filter(
                    account=invoice_refreshed.account,
                    product=item_product,
                ).aggregate(models.Sum("quantity"))["quantity__sum"]
                or Decimal("0")
            )
        elif item_ingredient:
            current_balance = (
                StockMovement.all_objects.filter(
                    account=invoice_refreshed.account,
                    ingredient=item_ingredient,
                ).aggregate(models.Sum("quantity"))["quantity__sum"]
                or Decimal("0")
            )

        entry_qty = abs(entry_mov.quantity)
        has_partial_consumption = current_balance < entry_qty

        # Se houver consumo posterior e saldo menor que o que entrou, abre issue
        if has_partial_consumption:
            item_name = item_product.name if item_product else (item_ingredient.name if item_ingredient else "Item")
            NFeIssue.objects.create(
                account=invoice_refreshed.account,
                restaurant=invoice_refreshed.restaurant,
                branch=invoice_refreshed.branch,
                nfe=invoice_refreshed,
                issue_type=NFeIssue.TYPE_CANCELLED_AFTER_STOCK_MOVEMENT,
                description=(
                    f"A NF-e cancelada deu entrada de {entry_qty} {entry_mov.stock_unit} em '{item_name}', "
                    f"mas o saldo atual é de apenas {current_balance} {entry_mov.stock_unit}. "
                    f"Houve consumo ou venda prévia antes do cancelamento na SEFAZ."
                ),
                created_by=actor,
            )
            result["issues_created"] += 1

        # Criar movimento de reversão compensatório
        reversal_qty = -entry_qty
        reversal_total_cost = -abs(entry_mov.total_cost)

        reason_text = "Estorno por Cancelamento de NF-e na SEFAZ"
        if cancellation_protocol:
            reason_text += f" (Prot: {cancellation_protocol})"

        operator_user = actor or entry_mov.operator or (
            invoice_refreshed.stock_applied_by or invoice_refreshed.created_by
        )

        StockMovement.objects.create(
            account=invoice_refreshed.account,
            restaurant=invoice_refreshed.restaurant,
            branch=invoice_refreshed.branch,
            product=item_product,
            ingredient=item_ingredient,
            location=entry_mov.location,
            operator=operator_user,
            movement_type=StockMovement.TYPE_NFE_CANCELLATION_REVERSAL,
            quantity=reversal_qty,
            stock_unit=entry_mov.stock_unit,
            unit_cost=entry_mov.unit_cost,
            total_cost=reversal_total_cost,
            nfe=invoice_refreshed,
            nfe_item=entry_mov.nfe_item,
            receipt=entry_mov.receipt,
            receipt_item=entry_mov.receipt_item,
            inventory_lot=entry_mov.inventory_lot,
            reversal_of=entry_mov,
            reason=reason_text,
            created_by=operator_user,
            updated_by=operator_user,
        )
        result["reversals_created"] += 1

    return result
