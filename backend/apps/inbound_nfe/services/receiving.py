import datetime
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone

from apps.inbound_nfe.models import InboundNFe, InboundNFeItem, SupplierItemMapping
from apps.menu.models import Product, ProductUnitConversion
from apps.stock.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    InventoryLot,
    StockMovement,
)
from apps.assets.models import Asset, AssetLocationHistory


def calculate_stock_unit_cost(item: InboundNFeItem, stock_quantity: Decimal) -> Decimal:
    """
    Calcula o custo unitário real para o estoque com base no valor do produto e despesas acessórias.
    """
    if stock_quantity <= 0:
        return Decimal("0")

    total_item_cost = (
        item.product_total
        - item.discount
        + item.freight
        + item.insurance
        + item.other_expenses
    )
    return round(total_item_cost / stock_quantity, 4)


def update_product_average_cost(product: Product, new_qty: Decimal, new_cost: Decimal):
    """
    Atualiza o custo médio ponderado e o último custo de compra do produto.
    O preço de venda (sale_price) NÃO é alterado pelo recebimento fiscal;
    permanece o valor cobrado definido pelo gerente.
    """
    if not product or new_qty <= 0 or new_cost <= 0:
        return

    total_balance = (
        StockMovement.all_objects.filter(product=product)
        .aggregate(models.Sum("quantity"))["quantity__sum"]
        or Decimal("0")
    )

    # O movimento da entrada recém-criado já consta no total_balance.
    # Subtraímos new_qty para obter o saldo anterior real em estoque.
    previous_balance = max(Decimal("0"), total_balance - new_qty)
    current_avg = product.current_average_cost or Decimal("0")

    if previous_balance > Decimal("0") and current_avg > Decimal("0"):
        new_total_qty = previous_balance + new_qty
        new_total_val = (previous_balance * current_avg) + (new_qty * new_cost)
        product.current_average_cost = round(new_total_val / new_total_qty, 4)
    else:
        product.current_average_cost = round(new_cost, 4)

    product.last_purchase_cost = round(new_cost, 4)
    product.estimated_cost = round(product.current_average_cost, 2)

    # Recalcula margem percentual caso o gerente já tenha definido sale_price
    if product.sale_price and product.sale_price > 0:
        product.margin_percent = round(
            ((product.sale_price - product.estimated_cost) / product.sale_price) * 100, 2
        )
    else:
        product.margin_percent = Decimal("0.00")

    product.save(update_fields=["current_average_cost", "last_purchase_cost", "estimated_cost", "margin_percent"])


@transaction.atomic
def receive_invoice(
    invoice_id=None,
    user=None,
    location=None,
    items_data=None,
    receipt_notes="",
    *,
    invoice=None,
    received_by=None,
    items_payload=None,
    notes=None,
):
    """
    Realiza o recebimento físico e fiscal da NF-e:
    1. Cria GoodsReceipt e GoodsReceiptItem registrando divergências
    2. Cria StockMovement e InventoryLot (para produtos de consumo/lote/reutilizáveis)
    3. Cria instâncias de Asset (para produtos serializados / equipamentos)
    4. Atualiza custo médio e histórico de aprendizado do fornecedor
    """
    # Aceita os nomes usados pela view atual e pela API de servico original.
    invoice_id = getattr(invoice, "pk", invoice_id)
    user = received_by or user
    items_data = items_payload if items_payload is not None else (items_data or [])
    receipt_notes = notes if notes is not None else receipt_notes
    invoice = InboundNFe.all_objects.select_for_update().get(id=invoice_id)

    if invoice.status == InboundNFe.STATUS_RECEIVED:
        raise ValueError("Esta NF-e já foi recebida e aplicada ao estoque.")

    if invoice.status == InboundNFe.STATUS_CANCELLED:
        raise ValueError("Não é possível receber uma NF-e cancelada.")

    if invoice.status == InboundNFe.STATUS_IGNORED:
        raise ValueError("Esta NF-e está marcada como ignorada e não pode ser recebida no estoque. Reative a nota para prosseguir.")

    items = list(InboundNFeItem.all_objects.select_for_update().filter(invoice=invoice))
    if not items:
        raise ValueError("Esta NF-e não possui itens para receber.")

    active_items = [i for i in items if not i.is_ignored]
    if not active_items:
        raise ValueError("Todos os itens desta NF-e foram ignorados. Não há produtos para dar entrada no estoque.")

    items_dict = {str(item_data["item_id"]): item_data for item_data in items_data}

    # Gerar número sequencial de recebimento
    last_receipt = GoodsReceipt.all_objects.filter(account=invoice.account).order_by("-created_at").first()
    next_num = 1
    if last_receipt and last_receipt.receipt_number and last_receipt.receipt_number.startswith("REC-"):
        try:
            next_num = int(last_receipt.receipt_number.split("-")[-1]) + 1
        except (IndexError, ValueError):
            next_num = 1
    receipt_number = f"REC-{next_num:06d}"

    receipt = GoodsReceipt.objects.create(
        account=invoice.account,
        restaurant=invoice.restaurant,
        branch=invoice.branch,
        invoice=invoice,
        receipt_number=receipt_number,
        received_by=user,
        status=GoodsReceipt.STATUS_CONFIRMED,
        notes=receipt_notes,
        location=location,
    )

    has_divergence = False

    for item in items:
        if item.is_ignored:
            continue

        item_id_str = str(item.id)
        item_data = items_dict.get(item_id_str, {})

        product = item.product
        if not product and item.ingredient:
            # Fallback para vincular a produto existente se houver
            product = getattr(item.ingredient, "product", None) or Product.all_objects.filter(
                account=invoice.account,
                name__iexact=item.ingredient.name,
            ).first()

        if not product and not item.ingredient:
            raise ValueError(f"O item '{item.description}' não possui um produto ou insumo vinculado.")

        # Fator de conversão e quantidades
        conversion_factor = Decimal(str(item_data.get("conversion_factor", item.conversion_factor or 1)))
        item.conversion_factor = conversion_factor

        # Quantidade esperada (convertida para unidade de estoque)
        expected_quantity = item.commercial_quantity * conversion_factor

        # Quantidade conferida/recebida fisicamente
        if "received_quantity" in item_data:
            received_quantity = Decimal(str(item_data["received_quantity"]))
        else:
            received_quantity = expected_quantity

        accepted_quantity = Decimal(str(item_data.get("accepted_quantity", received_quantity)))
        rejected_quantity = Decimal(str(item_data.get("rejected_quantity", max(Decimal("0"), expected_quantity - accepted_quantity))))
        difference_quantity = received_quantity - expected_quantity

        if difference_quantity != 0 or rejected_quantity > 0:
            has_divergence = True

        unit_cost = calculate_stock_unit_cost(item, accepted_quantity) if accepted_quantity > 0 else Decimal("0")
        total_cost = accepted_quantity * unit_cost

        lot_number = str(item_data.get("lot_number", "")).strip()
        exp_date_raw = item_data.get("expiration_date")
        mfg_date_raw = item_data.get("manufacturing_date")
        serials = item_data.get("serials", [])
        item_notes = str(item_data.get("notes", "")).strip()

        # Criar item de conferência física
        receipt_item = GoodsReceiptItem.objects.create(
            account=invoice.account,
            restaurant=invoice.restaurant,
            branch=invoice.branch,
            receipt=receipt,
            nfe_item=item,
            product=product or Product.all_objects.filter(account=invoice.account).first(),
            expected_quantity=expected_quantity,
            received_quantity=received_quantity,
            difference_quantity=difference_quantity,
            accepted_quantity=accepted_quantity,
            rejected_quantity=rejected_quantity,
            unit_cost=unit_cost,
            total_cost=total_cost,
            lot_number=lot_number,
            expiration_date=exp_date_raw,
            manufacturing_date=mfg_date_raw,
            serials=serials if isinstance(serials, list) else [],
            notes=item_notes,
        )

        item.received_quantity = received_quantity

        # Se for item serializado / equipamento patrimonial
        if product and (
            product.tracking_mode == Product.TRACKING_SERIALIZED
            or product.item_type in [Product.ITEM_EQUIPMENT, Product.ITEM_FIXED_ASSET]
            or product.requires_serial_number
        ):
            num_assets = int(accepted_quantity)
            warranty_months = product.default_useful_life_months or 12
            today = timezone.now().date()
            warranty_end = today + datetime.timedelta(days=warranty_months * 30)

            for idx in range(num_assets):
                serial = serials[idx] if (isinstance(serials, list) and idx < len(serials)) else ""
                asset = Asset.objects.create(
                    account=invoice.account,
                    restaurant=invoice.restaurant,
                    branch=invoice.branch,
                    product=product,
                    nfe=invoice,
                    nfe_item=item,
                    receipt=receipt,
                    supplier_cnpj=invoice.supplier_cnpj,
                    supplier_name=invoice.supplier_name,
                    purchase_date=invoice.issue_date.date() if invoice.issue_date else today,
                    received_date=today,
                    purchase_price=unit_cost,
                    brand=product.brand,
                    model=product.model,
                    serial_number=str(serial).strip(),
                    location=location,
                    status=Asset.STATUS_IN_USE,
                    warranty_start_date=today,
                    warranty_end_date=warranty_end,
                    warranty_months=warranty_months,
                    warranty_provider=invoice.supplier_name,
                    notes=f"Entrada via NF-e {invoice.number}",
                )
                AssetLocationHistory.objects.create(
                    account=invoice.account,
                    restaurant=invoice.restaurant,
                    branch=invoice.branch,
                    asset=asset,
                    from_location=None,
                    to_location=location,
                    moved_by=user,
                    reason=f"Recebimento inicial NF-e {invoice.number}",
                )
        else:
            # Item de estoque normal / lote / consumo / reutilizável
            target_location = location
            if product and product.item_type == Product.ITEM_REUSABLE:
                from apps.stock.models import StockLocation
                general_loc = (
                    StockLocation.all_objects
                    .filter(account=invoice.account, restaurant=invoice.restaurant)
                    .filter(name__icontains="GERAL")
                    .first()
                    or StockLocation.all_objects
                    .filter(account=invoice.account, restaurant=invoice.restaurant)
                    .filter(name__icontains="DEPÓSITO")
                    .first()
                )
                if general_loc:
                    target_location = general_loc

            lot_obj = None
            if accepted_quantity > 0:
                if lot_number or exp_date_raw or (product and (product.requires_lot_control or product.requires_expiration_control)):
                    lot_obj = InventoryLot.objects.create(
                        account=invoice.account,
                        restaurant=invoice.restaurant,
                        branch=invoice.branch,
                        product=product or Product.all_objects.filter(account=invoice.account).first(),
                        lot_number=lot_number or f"LOTE-{invoice.number}-{item.item_number}",
                        supplier_cnpj=invoice.supplier_cnpj,
                        supplier_name=invoice.supplier_name,
                        nfe=invoice,
                        receipt=receipt,
                        receipt_item=receipt_item,
                        location=target_location,
                        manufacturing_date=mfg_date_raw,
                        expiration_date=exp_date_raw,
                        initial_quantity=accepted_quantity,
                        available_quantity=accepted_quantity,
                        unit_cost=unit_cost,
                        total_cost=total_cost,
                        status=InventoryLot.STATUS_ACTIVE,
                    )

                movement = StockMovement.objects.create(
                    account=invoice.account,
                    restaurant=invoice.restaurant,
                    branch=invoice.branch,
                    product=product,
                    ingredient=item.ingredient,
                    location=target_location,
                    operator=user,
                    movement_type=StockMovement.TYPE_PURCHASE_ENTRY,
                    quantity=accepted_quantity,
                    stock_unit=product.stock_unit if product else "UN",
                    unit_cost=unit_cost,
                    total_cost=total_cost,
                    nfe=invoice,
                    nfe_item=item,
                    receipt=receipt,
                    receipt_item=receipt_item,
                    inventory_lot=lot_obj,
                    reason=f"Entrada NF-e {invoice.number} - {invoice.supplier_name}",
                )
                item.stock_movement = movement

                if product:
                    update_product_average_cost(product, accepted_quantity, unit_cost)
                elif item.ingredient:
                    from apps.menu.services import update_ingredient_average_cost
                    update_ingredient_average_cost(item.ingredient, accepted_quantity, unit_cost)

        item.save(update_fields=["received_quantity", "conversion_factor", "stock_movement"])

        # Salvar aprendizado do fornecedor
        if product and invoice.supplier_cnpj:
            target_restaurant = invoice.restaurant or getattr(product, "restaurant", None)
            target_branch = invoice.branch or getattr(product, "branch", None)

            mapping_defaults = {
                "restaurant": target_restaurant,
                "branch": target_branch,
                "product": product,
                "ingredient": item.ingredient,
                "supplier_description": item.description,
                "conversion_factor": conversion_factor,
                "confirmed_by_user": True,
            }

            SupplierItemMapping.save_mapping(
                account=invoice.account,
                supplier_cnpj=invoice.supplier_cnpj,
                supplier_code=item.supplier_code,
                supplier_ean=item.ean,
                defaults=mapping_defaults,
            )
            # Salvar conversão de unidade se houver unidade comercial diferente
            if item.commercial_unit and item.commercial_unit.upper() != product.stock_unit.upper():
                ProductUnitConversion.objects.update_or_create(
                    account=invoice.account,
                    product=product,
                    source_unit=item.commercial_unit.upper(),
                    supplier_cnpj=invoice.supplier_cnpj,
                    supplier_product_code=item.supplier_code,
                    defaults={
                        "restaurant": target_restaurant,
                        "branch": target_branch,
                        "target_unit": product.stock_unit.upper(),
                        "factor": conversion_factor,
                    },
                )

    if has_divergence:
        receipt.status = GoodsReceipt.STATUS_DIVERGENT
        receipt.save(update_fields=["status"])

    invoice.status = InboundNFe.STATUS_RECEIVED
    invoice.stock_applied_at = timezone.now()
    invoice.stock_applied_by = user
    invoice.save(update_fields=["status", "stock_applied_at", "stock_applied_by"])

    return receipt
