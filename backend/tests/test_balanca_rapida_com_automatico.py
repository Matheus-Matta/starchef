"""Balança com "lançar e imprimir automaticamente" ligado e a Balança Rápida.

A estação registra a leitura e, em seguida, lança ela mesma na comanda. O
automático da balança consumia a leitura no registro — no modo balcão abrindo
um pedido de balcão fantasma — e o lançamento falhava SEMPRE com "Leitura
invalida, instavel ou ja utilizada".
"""
from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import CommandItem, Order
from apps.printers.models import Printer, Scale
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def balanca(account, restaurant, branch):
    buffet = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Buffet",
        internal_code="BUF-AUTO", sale_price=Decimal("59.90"), pricing_unit=Product.PRICING_KG,
    )
    # A impressora da balança é o que faz o automático FUNCIONAR (e consumir a
    # leitura): sem ela o lançamento automático desiste e a leitura fica livre.
    impressora = Printer.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Térmica",
        connection_type="network", host="10.0.0.9", driver_type="escpos", is_active=True,
    )
    return Scale.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Balança",
        product=buffet, auto_print=True, printer=impressora,
    )


def _pesar_e_lancar(admin_client, balanca, comanda, **marca):
    leitura = admin_client.post(
        "/api/v1/scales/readings/",
        {"scale": str(balanca.id), "weight_kg": "0.480", "is_stable": True, "source": "agent", **marca},
        format="json",
    )
    assert leitura.status_code == 201, leitura.json()
    return admin_client.post(
        f"/api/v1/scales/{balanca.id}/checkout-command/",
        {"command_code": str(comanda.number), "scale_reading": leitura.json()["id"], "print": False},
        format="json",
    )


def test_leitura_da_balanca_rapida_lanca_na_comanda_com_o_automatico_ligado(
    admin_client, account, restaurant, branch, balanca
):
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=31)

    resposta = _pesar_e_lancar(admin_client, balanca, comanda, for_checkout=True)

    assert resposta.status_code == 201, resposta.json()
    assert CommandItem.all_objects.filter(command=comanda, quantity=Decimal("0.480")).exists()
    assert not Order.all_objects.exists()  # nenhum pedido de balcão fantasma


def test_sem_a_marca_o_automatico_consome_a_leitura(admin_client, account, restaurant, branch, balanca):
    """O defeito, para o teste acima provar alguma coisa."""
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=32)

    resposta = _pesar_e_lancar(admin_client, balanca, comanda)

    assert resposta.status_code == 400
    assert Order.all_objects.exists()


def test_etiqueta_de_pesagem_da_comanda_sai_com_codigo_de_barras_sem_qr(
    admin_client, account, restaurant, branch, balanca
):
    """É o papel que o cliente leva ao caixa: sem o código, o caixa digitava."""
    from apps.printers.models import PrintJob

    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=33)
    leitura = admin_client.post(
        "/api/v1/scales/readings/",
        {"scale": str(balanca.id), "weight_kg": "0.300", "is_stable": True, "for_checkout": True},
        format="json",
    )
    resposta = admin_client.post(
        f"/api/v1/scales/{balanca.id}/checkout-command/",
        {"command_code": "33", "scale_reading": leitura.json()["id"]},
        format="json",
    )

    assert resposta.status_code == 201, resposta.json()
    payload = PrintJob.all_objects.get(job_type=PrintJob.TYPE_WEIGH).payload
    codigo = comanda.code or "33"
    assert payload["payload_version"] == 2
    assert payload["barcode"] == {"symbology": "CODE128", "value": codigo}
    assert "qr_data" not in payload
