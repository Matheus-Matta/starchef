from decimal import Decimal

import pytest
from django.utils import timezone

from apps.inbound_nfe.models import InboundNFe, InboundNFeItem, SupplierItemMapping
from apps.menu.models import Ingredient, Product

CNPJ = "00074569004784"


def _nota(account, restaurant, status, chave, insumo):
    nota = InboundNFe.all_objects.create(
        account=account, restaurant=restaurant, access_key=chave, number="1",
        series="10", supplier_cnpj=CNPJ, issue_date=timezone.now(), status=status,
    )
    return InboundNFeItem.all_objects.create(
        account=account, restaurant=restaurant, invoice=nota, item_number=1,
        supplier_code="110333", description="FANTA LARANJA KS ULTRA 290ML CX 24UN",
        ingredient=insumo, conversion_factor=Decimal("24"),
    )


@pytest.mark.django_db
def test_transformar_insumo_em_produto_copia_os_dados_e_leva_so_o_que_nao_entrou(
    admin_client, account, restaurant
):
    """A nota de bebidas foi ligada a INSUMOS. Transformar cria o produto com os
    mesmos dados e passa para ele as notas pendentes e o aprendizado do
    fornecedor; a nota já recebida continua no insumo, onde o saldo entrou."""
    insumo = Ingredient.objects.create(
        account=account, restaurant=restaurant, name="FANTA LARANJA CX24",
        unit=Ingredient.UNIT_KG, average_cost=Decimal("1.8890"),
        minimum_stock=Decimal("12"),
    )
    pendente = _nota(account, restaurant, InboundNFe.STATUS_PENDING_RECEIPT, "3" * 44, insumo)
    recebida = _nota(account, restaurant, InboundNFe.STATUS_RECEIVED, "4" * 44, insumo)
    SupplierItemMapping.all_objects.create(
        account=account, restaurant=restaurant, supplier_cnpj=CNPJ,
        supplier_code="110333", ingredient=insumo,
    )

    resposta = admin_client.post(
        f"/api/v1/menu/ingredients/{insumo.id}/to-product/",
        {"restaurant": str(restaurant.id)}, format="json",
    )

    assert resposta.status_code == 201, resposta.json()
    produto = Product.all_objects.get(pk=resposta.json()["id"])
    assert (produto.name, produto.stock_unit) == ("FANTA LARANJA CX24", "KG")
    assert produto.current_average_cost == Decimal("1.8890")
    assert produto.estimated_cost == Decimal("1.89")
    assert produto.minimum_stock == Decimal("12")
    assert produto.restaurant_id == restaurant.id
    pendente.refresh_from_db()
    recebida.refresh_from_db()
    assert (pendente.product_id, pendente.ingredient_id) == (produto.id, None)
    assert pendente.conversion_factor == Decimal("24")
    assert recebida.ingredient_id == insumo.id
    assert SupplierItemMapping.all_objects.get(supplier_code="110333").product_id == produto.id
    insumo.refresh_from_db()
    assert insumo.deleted_at is None


@pytest.mark.django_db
def test_insumo_da_conta_vira_produto_do_unico_restaurante_sem_informar(
    admin_client, account, restaurant
):
    """O insumo é da conta (sem restaurante) e o produto exige um. A tela não
    manda no corpo: vale o da barra lateral, ou o único restaurante da conta."""
    insumo = Ingredient.objects.create(account=account, name="SPRITE CX24")

    resposta = admin_client.post(f"/api/v1/menu/ingredients/{insumo.id}/to-product/", {}, format="json")

    assert resposta.status_code == 201, resposta.json()
    produto = Product.all_objects.get(pk=resposta.json()["id"])
    assert produto.restaurant_id == restaurant.id
    assert produto.stock_unit == "UN"
