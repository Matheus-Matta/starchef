"""As rotas do cupom, pelo que o caixa consegue fazer sem cobrar nada ainda.

O verbo que o cupom tem e a promoção não: CONFERIR. O caixa precisa saber se
aquele código vale para AQUELE pedido enquanto o cliente ainda está falando — e
conferir não pode consumir. Aplicar para depois desfazer queimaria o limite de
um cupom de uso único num pedido que o cliente desistiu de fechar.
"""

import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Product, ProductCategory
from apps.promotions.models import Coupon

pytestmark = pytest.mark.django_db


@pytest.fixture
def categoria(account, restaurant, branch):
    return ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Bebidas"
    )


@pytest.fixture
def produto(account, restaurant, branch, categoria):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=categoria,
        name="Refrigerante", internal_code=f"R{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("20.00"),
    )


def _tabela(api_client, **campos):
    corpo = {"name": f"Tabela {uuid.uuid4().hex[:6]}", "is_enabled": True, **campos}
    resp = api_client.post("/api/v1/promotions/discount-tables/", corpo, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def test_cupom_normaliza_o_codigo_e_recusa_espaco(api_client):
    resp = api_client.post(
        "/api/v1/promotions/coupons/",
        {"code": " natal10 ", "discount_kind": "percent", "discount_value": "10"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["code"] == "NATAL10"

    # Espaço no meio é o que faz o cliente ditar errado no telefone.
    ruim = api_client.post(
        "/api/v1/promotions/coupons/",
        {"code": "NATAL 10", "discount_kind": "percent", "discount_value": "10"},
        format="json",
    )
    assert ruim.status_code == 400



def test_teto_so_faz_sentido_no_percentual(api_client):
    resp = api_client.post(
        "/api/v1/promotions/coupons/",
        {"code": "FIXO", "discount_kind": "amount", "discount_value": "10", "max_discount_amount": "5"},
        format="json",
    )
    assert resp.status_code == 400
    assert "percentual" in str(resp.data)



def test_conferir_o_cupom_nao_consome_o_cupom(api_client, account, restaurant, branch, manager_user, produto):
    """O caixa confere enquanto o cliente fala — e nada muda no pedido."""
    from apps.core.tenant import tenant_context
    from apps.orders.models import Order
    from apps.orders.services import add_order_item, create_order

    with tenant_context(account):
        pedido = create_order(restaurant=restaurant, branch=branch, user=manager_user, order_type=Order.TYPE_COUNTER)
        add_order_item(order=pedido, product=produto, quantity=3, user=manager_user)  # 60,00
    cupom = Coupon.objects.create(
        account=account, code="DEZ", discount_kind="percent", discount_value=Decimal("10"),
    )

    resp = api_client.post(
        "/api/v1/promotions/coupons/validate/",
        {"code": "dez", "order": str(pedido.id)},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["valid"] is True
    assert Decimal(str(resp.data["discount"])) == Decimal("6.00")
    # Nada foi resgatado, e o pedido segue sem cupom preso.
    assert cupom.redemptions.count() == 0
    pedido.refresh_from_db()
    assert pedido.coupon_id is None



def test_conferencia_devolve_o_motivo_da_recusa(api_client, account, restaurant, branch, manager_user, produto):
    from apps.core.tenant import tenant_context
    from apps.orders.models import Order
    from apps.orders.services import add_order_item, create_order

    with tenant_context(account):
        pedido = create_order(restaurant=restaurant, branch=branch, user=manager_user, order_type=Order.TYPE_COUNTER)
        add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)  # 20,00
    Coupon.objects.create(
        account=account, code="CEM", discount_kind="percent", discount_value=Decimal("10"),
        minimum_order_value=Decimal("100.00"),
    )

    resp = api_client.post(
        "/api/v1/promotions/coupons/validate/", {"code": "CEM", "order": str(pedido.id)}, format="json"
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["valid"] is False
    assert "a partir de R$ 100,00 em produtos" in resp.data["reason"]



def test_cupom_inexistente_e_422_com_o_codigo_na_mensagem(api_client, account, restaurant, branch, manager_user):
    """422, e não 400: o corpo está certo e o código foi digitado certo."""
    from apps.core.tenant import tenant_context
    from apps.orders.models import Order
    from apps.orders.services import create_order

    with tenant_context(account):
        pedido = create_order(restaurant=restaurant, branch=branch, user=manager_user, order_type=Order.TYPE_COUNTER)

    resp = api_client.post(
        "/api/v1/promotions/coupons/validate/", {"code": "NAOEXISTE", "order": str(pedido.id)}, format="json"
    )
    assert resp.status_code == 422, resp.data
    assert resp.json()["error"]["code"] == "coupon_rejected"
    assert "NAOEXISTE" in str(resp.json()["error"]["message"])
