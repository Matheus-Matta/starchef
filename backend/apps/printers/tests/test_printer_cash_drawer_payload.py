"""O que o PDV recebe sobre a gaveta, que e o que decide o pulso.

`printer_payload` e montado a mao, e nao pelo serializer: todo campo novo da
impressora precisa ser lembrado ali. A gaveta ja nasceu esquecida uma vez — o
cupom da venda em dinheiro saia normalmente, o PDV recebia a impressora sem os
campos da gaveta, e o pulso nunca chegava a ser montado. Nada falhava; a gaveta
so nao abria.
"""
import pytest

from apps.printers.models import Printer
from apps.printers.services import printer_payload

pytestmark = pytest.mark.django_db


def _printer(account, restaurant, branch, **overrides):
    campos = {
        "name": "Caixa 01",
        "driver_type": Printer.DRIVER_ESCPOS,
        "connection_type": Printer.CONNECTION_NETWORK,
        "host": "192.168.10.50",
        "port": 9100,
    }
    campos.update(overrides)
    return Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        **campos,
    )


def test_printer_payload_carrega_a_gaveta(account, restaurant, branch):
    impressora = _printer(
        account,
        restaurant,
        branch,
        cash_drawer_pin=Printer.DRAWER_PIN_5,
        cash_drawer_on_ms=120,
        cash_drawer_off_ms=480,
    )

    payload = printer_payload(impressora)

    assert payload["cash_drawer_enabled"] is True
    assert payload["cash_drawer_pin"] == 5
    assert payload["cash_drawer_on_ms"] == 120
    assert payload["cash_drawer_off_ms"] == 480


def test_printer_payload_ignora_a_coluna_velha(account, restaurant, branch):
    """Uma linha gravada antes desta mudanca tem `False` na coluna.

    O PDV instalado no balcao acredita no que o payload diz. Derivar do driver
    aqui e o que faz a gaveta abrir nesses terminais sem esperar a atualizacao
    de cada um deles.
    """
    impressora = _printer(
        account,
        restaurant,
        branch,
        name="Caixa 02",
        host="192.168.10.51",
    )
    Printer.objects.filter(pk=impressora.pk).update(cash_drawer_enabled=False)
    impressora.refresh_from_db()
    assert impressora.cash_drawer_enabled is False

    assert printer_payload(impressora)["cash_drawer_enabled"] is True


def test_printer_payload_nao_promete_gaveta_fora_do_escpos(account, restaurant, branch):
    """No driver grafico os bytes do pulso sairiam impressos no papel."""
    impressora = _printer(
        account,
        restaurant,
        branch,
        name="Caixa 03",
        host="192.168.10.52",
        driver_type=Printer.DRIVER_BROWSER,
    )

    assert printer_payload(impressora)["cash_drawer_enabled"] is False
