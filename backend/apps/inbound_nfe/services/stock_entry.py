"""Espelha o recebimento fiscal na tela operacional de entradas de estoque.

O movimento continua sendo criado uma vez so pelo recebimento da NF-e. Este
modulo cria o documento, sua linha e o lote etiquetavel, que passam a apontar
para aquele mesmo movimento.
"""
import re
from decimal import Decimal

from django.utils import timezone

from apps.stock.models import StockEntry, StockEntryItem, StockLot, Supplier


def criar_entrada_da_nfe(*, invoice, location, user, notes=""):
    numero = f"NF-e {invoice.number}"
    if invoice.series:
        numero += f"/{invoice.series}"
    data = invoice.issue_date.date() if invoice.issue_date else timezone.localdate()
    return StockEntry.objects.create(
        account=invoice.account,
        restaurant=location.restaurant,
        branch=location.branch,
        location=location,
        effective_date=data,
        supplier=invoice.supplier_name,
        document_number=numero,
        notes=notes,
        status=StockEntry.STATUS_POSTED,
        posted_at=timezone.now(),
        posted_by=user,
        created_by=user,
        updated_by=user,
    )


def _fornecedor_da_nfe(invoice):
    documento = re.sub(r"\D", "", invoice.supplier_cnpj or "")
    if documento:
        encontrado = Supplier.all_objects.filter(account=invoice.account, tax_id=documento).first()
        if encontrado:
            return encontrado
    return Supplier.all_objects.filter(
        account=invoice.account, name__iexact=invoice.supplier_name
    ).first()


def registrar_linha_e_lote(
    *, entry, nfe_item, accepted_quantity, unit_cost, lot_number,
    manufacturing_date, expiration_date, user, create_lot, location=None,
):
    """Cria a linha visivel e, quando ha saldo fisico, seu lote etiquetavel."""
    product = nfe_item.product
    ingredient = nfe_item.ingredient
    stock_item = product or ingredient
    unit = product.stock_unit if product else ingredient.unit
    quantity = Decimal(str(accepted_quantity)).quantize(Decimal("0.001"))
    line = StockEntryItem.objects.create(
        account=entry.account,
        restaurant=entry.restaurant,
        branch=entry.branch,
        entry=entry,
        ingredient=ingredient,
        product=product,
        supplier=_fornecedor_da_nfe(nfe_item.invoice),
        package_quantity=quantity,
        content_per_package=1,
        content_unit=unit,
        base_quantity=quantity,
        unit_cost=unit_cost,
        total_cost=(quantity * Decimal(str(unit_cost))).quantize(Decimal("0.01")),
        supplier_lot=lot_number,
        manufactured_at=manufacturing_date,
        expires_at=expiration_date,
        label_count=1,
        notes=nfe_item.description[:200],
        created_by=user,
        updated_by=user,
    )
    if not create_lot or quantity <= 0:
        return line, None
    lot = StockLot.objects.create(
        account=entry.account,
        restaurant=entry.restaurant,
        branch=entry.branch,
        ingredient=ingredient,
        product=product,
        location=location or entry.location,
        entry_item=line,
        code=StockLot.build_code(stock_item),
        supplier_lot=lot_number,
        entered_at=entry.effective_date,
        manufactured_at=manufacturing_date,
        expires_at=expiration_date,
        initial_quantity=quantity,
        quantity=quantity,
        unit_cost=unit_cost,
        created_by=user,
        updated_by=user,
    )
    return line, lot


def cancelar_entrada_espelhada(movement, *, user):
    """Mantem a entrada e o lote coerentes quando a SEFAZ cancela a nota."""
    if movement.lot_id:
        movement.lot.quantity = Decimal("0")
        movement.lot.status = StockLot.STATUS_DISCARDED
        movement.lot.updated_by = user
        movement.lot.save(update_fields=["quantity", "status", "updated_by", "updated_at"])
    if movement.entry_id and movement.entry.status != StockEntry.STATUS_CANCELLED:
        movement.entry.status = StockEntry.STATUS_CANCELLED
        movement.entry.cancelled_at = timezone.now()
        movement.entry.cancelled_by = user
        movement.entry.updated_by = user
        movement.entry.save(update_fields=[
            "status", "cancelled_at", "cancelled_by", "updated_by", "updated_at",
        ])
