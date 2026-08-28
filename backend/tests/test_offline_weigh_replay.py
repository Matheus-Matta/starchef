"""Replay de uma pesagem feita com o PDV offline.

Criar um ``ScaleReading`` exige servidor. Quando a internet cai, a estacao de
balanca le o peso pela porta serial, converte em item na copia local e enfileira
o ``checkout-command`` com o **peso bruto** — nao ha id de leitura para citar.

Sem aceitar esse formato, a operacao voltava da fila com 400 e a pesagem ficava
presa na tela de revisao: o cliente ja tinha levado o prato e o item nunca
chegava ao pedido no servidor.
"""

from decimal import Decimal

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.menu.models import Product
from apps.printers.models import Printer, Scale, ScaleReading


@pytest.fixture
def authenticated(api_client, manager_user):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )
    return api_client


@pytest.fixture
def weighed_product(account, restaurant, branch, category):
    product = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        category=category,
        name="Buffet por quilo",
        internal_code="BUF001",
        sale_price=Decimal("59.90"),
        pricing_unit=Product.PRICING_KG,
    )
    product.restaurants.add(restaurant)
    return product


@pytest.fixture
def scale(account, restaurant, branch, weighed_product):
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balcao",
        connection_type=Printer.CONNECTION_NETWORK,
        host="127.0.0.1",
        port=9100,
    )
    return Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balanca do buffet",
        product=weighed_product,
        printer=printer,
    )


@pytest.mark.django_db
def test_peso_bruto_materializa_a_leitura_e_lanca_o_item(
    authenticated, scale, command, weighed_product
):
    response = authenticated.post(
        f"/api/v1/scales/{scale.pk}/checkout-command/",
        {"command_code": command.code, "weight_kg": "0.412"},
        format="json",
    )

    assert response.status_code == 201, response.content
    # `all_objects` porque o manager padrao e escopado por tenant e o teste
    # consulta fora do ciclo da requisicao.
    reading = ScaleReading.all_objects.filter(scale=scale).first()
    assert reading is not None
    assert reading.weight_kg == Decimal("0.412")
    assert reading.is_stable is True
    # A leitura fica ligada ao item: e o que impede a mesma pesagem de ser
    # aproveitada duas vezes.
    assert reading.order_item is not None
    assert reading.order_item.product_id == weighed_product.pk


@pytest.mark.django_db
def test_sem_leitura_e_sem_peso_continua_recusando(authenticated, scale, command):
    response = authenticated.post(
        f"/api/v1/scales/{scale.pk}/checkout-command/",
        {"command_code": command.code},
        format="json",
    )

    assert response.status_code == 400
    assert "balanca" in str(response.data).lower()


@pytest.mark.django_db
def test_peso_invalido_e_recusado(authenticated, scale, command):
    for peso in ("0", "-1", "nao-e-numero"):
        response = authenticated.post(
            f"/api/v1/scales/{scale.pk}/checkout-command/",
            {"command_code": command.code, "weight_kg": peso},
            format="json",
        )
        assert response.status_code == 400, peso
