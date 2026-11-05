from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.inbound_nfe.models import InboundNFe, InboundNFeItem
from apps.inbound_nfe.services.cancellation import apply_cancellation
from apps.inbound_nfe.services.receiving import receive_invoice
from apps.menu.models import Product
from apps.stock.models import StockEntry, StockLocation, StockLot, StockMovement

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant(account):
    with tenant_context(account):
        yield


def test_confirmar_nfe_cria_entrada_com_produto_lote_e_validade(
    account, restaurant, branch, manager_user,
):
    """Produto sem Ingredient sumia de 'Itens recebidos' e nao tinha etiqueta."""
    location = StockLocation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Deposito",
    )
    product = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Queijo mussarela", internal_code="QUE-001", stock_unit="KG",
    )
    invoice = InboundNFe.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        access_key="1" * 44, number="123", series="1",
        supplier_name="Laticinios Brasil", supplier_cnpj="12345678000190",
        status=InboundNFe.STATUS_PENDING_RECEIPT,
    )
    nfe_item = InboundNFeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, invoice=invoice,
        item_number=1, description="QUEIJO MUSSARELA", supplier_code="Q-10",
        commercial_unit="KG", commercial_quantity=Decimal("10"),
        commercial_unit_value=Decimal("20"), product_total=Decimal("200"),
        product=product,
    )
    expires = timezone.localdate() + timedelta(days=30)

    receipt = receive_invoice(
        invoice_id=invoice.id, user=manager_user, location=location,
        items_data=[{
            "item_id": str(nfe_item.id), "accepted_quantity": Decimal("10"),
            "lot_number": "FORN-9", "expiration_date": expires,
        }],
    )

    entry = receipt.generated_stock_entry
    line = entry.items.get()
    lot = line.lots.get()
    movement = StockMovement.objects.get(nfe_item=nfe_item)
    assert entry.status == StockEntry.STATUS_POSTED
    assert line.product == product and line.ingredient is None
    assert lot.product == product and lot.expires_at == expires
    assert movement.entry == entry and movement.lot == lot

    apply_cancellation(invoice=invoice, actor=manager_user)
    entry.refresh_from_db()
    lot.refresh_from_db()
    assert entry.status == StockEntry.STATUS_CANCELLED
    assert lot.status == StockLot.STATUS_DISCARDED and lot.quantity == 0


def test_entrada_da_nfe_carrega_item_e_gera_code128(
    account, restaurant, branch, manager_user, api_client,
):
    """A tela recebe o nome do produto e a etiqueta usa barras, nao QR."""
    account.enabled_modules = ["logistica"]
    account.save(update_fields=["enabled_modules"])
    location = StockLocation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Deposito",
    )
    product = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Suco de uva", internal_code="SUC-01", stock_unit="UN",
    )
    invoice = InboundNFe.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        access_key="2" * 44, number="456", supplier_name="Fornecedor",
        status=InboundNFe.STATUS_PENDING_RECEIPT,
    )
    nfe_item = InboundNFeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, invoice=invoice,
        item_number=1, description="SUCO", commercial_unit="UN",
        commercial_quantity=Decimal("2"), commercial_unit_value=Decimal("5"),
        product_total=Decimal("10"), product=product,
    )
    entry = receive_invoice(
        invoice_id=invoice.id, user=manager_user, location=location,
        items_data=[{
            "item_id": str(nfe_item.id), "accepted_quantity": Decimal("2"),
            "expiration_date": timezone.localdate() + timedelta(days=10),
        }],
    ).generated_stock_entry

    detail = api_client.get(f"/api/v1/stock/entries/{entry.id}/")
    assert detail.status_code == 200
    assert detail.data["items"][0]["ingredient_name"] == "Suco de uva"
    assert detail.data["items"][0]["item_code"] == "SUC-01"

    with mock.patch("apps.stock.views.barcode_data_uri", return_value="code128") as barcode_mock:
        with mock.patch("apps.stock.views.qr_data_uri", return_value="qr") as qr_mock:
            labels = api_client.get(f"/api/v1/stock/entries/{entry.id}/labels/")
    assert labels.status_code == 200
    assert labels.data["labels"][0]["code_uri"] == "code128"
    assert labels.data["labels"][0]["expires_at"] is not None
    barcode_mock.assert_called_once_with(StockLot.all_objects.get(entry_item__entry=entry).code)
    qr_mock.assert_not_called()
