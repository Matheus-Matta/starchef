from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.command_items import launch_item
from apps.orders.models import CommandBatch, CommandItem
from apps.printers.models import Scale, ScaleReading
from apps.restaurants.models import Command

A_CAMINHO = {CommandItem.STATUS_QUEUED, CommandItem.STATUS_SENT}


@pytest.mark.django_db
def test_checkout_da_balanca_manda_so_a_pesagem_para_a_producao(
    admin_client, admin_user, account, restaurant, branch
):
    """O prato pesado já está na mão do cliente: não fica "a enviar".

    O que o garçom anotou no mesmo cartão e segurou continua esperando — a
    balança manda só a própria pesagem, numa rodada só.
    """
    base = {"account": account, "restaurant": restaurant, "branch": branch}
    buffet = Product.objects.create(
        **base, name="Buffet", internal_code="BUF-PROD",
        sale_price=Decimal("59.90"), pricing_unit=Product.PRICING_KG,
    )
    agua = Product.objects.create(**base, name="Água", internal_code="AGUA-PROD", sale_price=Decimal("5"))
    sobremesa = Product.objects.create(**base, name="Pudim", internal_code="PUDIM", sale_price=Decimal("9"))
    scale = Scale.objects.create(**base, name="Balança", product=buffet)
    reading = ScaleReading.objects.create(
        **base, scale=scale, weight_kg=Decimal("0.400"), is_stable=True
    )
    command = Command.objects.create(**base, number=21)
    segurado = launch_item(command=command, product=sobremesa, user=admin_user)

    response = admin_client.post(
        f"/api/v1/scales/{scale.id}/checkout-command/",
        {
            "command_code": str(command.number),
            "scale_reading": str(reading.id),
            "extras": [{"product": str(agua.id), "quantity": 1}],
            "print": False,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    prato = CommandItem.all_objects.get(product=buffet)
    bebida = CommandItem.all_objects.get(product=agua)
    assert prato.status in A_CAMINHO
    assert bebida.status in A_CAMINHO
    assert prato.batch_id == bebida.batch_id
    assert CommandBatch.all_objects.filter(command=command).count() == 1
    # Enviar não é cobrar: continua na comanda até o caixa.
    assert prato.command_status == CommandItem.STATUS_PENDENTE
    segurado.refresh_from_db()
    assert segurado.status == CommandItem.STATUS_PENDING
    assert segurado.batch_id is None
