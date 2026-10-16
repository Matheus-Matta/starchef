"""A estação escolhe o produto por quilo a cada pesagem.

O PDV manda só QUAL produto; o preço é do servidor. E só produto por quilo
entra: uma bebida "pesada" viraria 0,450 unidade cobrada pelo preço cheio.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.models import CommandItem
from apps.printers.models import Scale

pytestmark = pytest.mark.django_db


def _produto(balanca, nome, preco, unidade):
    with tenant_context(balanca.account):
        return Product.objects.create(
            account=balanca.account, restaurant=balanca.restaurant, branch=balanca.branch,
            category=balanca.product.category, name=nome, internal_code=f"P{uuid.uuid4().hex[:6]}",
            sale_price=Decimal(preco), pricing_unit=unidade,
        )


def _pesar(client, balanca, produto):
    return client.post(
        f"/api/v1/scales/{balanca.id}/checkout-command/",
        {"command_code": "1", "weight_kg": "0.500", "print": False, "weighed_product": produto},
        format="json",
    )


def test_o_produto_escolhido_vence_o_da_balanca_com_o_preco_do_servidor(
    admin_client, balanca, comandas, account
):
    churrasco = _produto(balanca, "Churrasco por kg", "89.90", Product.PRICING_KG)

    resposta = _pesar(admin_client, balanca, str(churrasco.id))

    assert resposta.status_code == 201, resposta.data
    with tenant_context(account):
        item = CommandItem.objects.get()
    assert item.product_id == churrasco.id
    assert item.unit_price == Decimal("89.90")
    assert item.total_price == Decimal("44.95")


def test_produto_que_nao_e_por_quilo_e_recusado(admin_client, balanca, comandas, account):
    refri = _produto(balanca, "Refrigerante", "6.00", Product.PRICING_UNIT)

    resposta = _pesar(admin_client, balanca, str(refri.id))

    assert resposta.status_code == 400
    with tenant_context(account):
        assert not CommandItem.objects.exists()


def test_balanca_sem_produto_vinculado_pesa_com_o_escolhido(admin_client, balanca, comandas):
    escolhido = _produto(balanca, "Sobremesa por kg", "49.90", Product.PRICING_KG)
    Scale.all_objects.filter(pk=balanca.pk).update(product=None)

    assert _pesar(admin_client, balanca, str(escolhido.id)).status_code == 201
    assert _pesar(admin_client, balanca, "").status_code == 400
