"""Cadastro da gaveta de dinheiro na impressora.

A gaveta nao tem cadastro proprio: ela e uma saida eletrica DA IMPRESSORA, e o
pulso que a destrava e um comando ESC/POS enviado no mesmo trabalho do cupom.
Por isso a validacao mora aqui, e nao num app de perifericos.
"""
import json

import pytest

pytestmark = pytest.mark.django_db


def _payload(restaurant, **overrides):
    body = {
        "name": "Caixa 01",
        "restaurant": str(restaurant.id),
        "driver_type": "escpos",
        "connection_type": "network",
        "host": "192.168.10.50",
        "port": 9100,
        "timeout_seconds": 10,
    }
    body.update(overrides)
    return body


def test_drawer_defaults_to_disabled(admin_client, restaurant):
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant)),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["cash_drawer_enabled"] is False


def test_drawer_settings_are_mirrored_into_settings(admin_client, restaurant):
    """O PDV guarda uma copia do cadastro junto do cupom na fila local e le os
    dois niveis — como ja faz com host, porta e timeout."""
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(
            _payload(
                restaurant,
                cash_drawer_enabled=True,
                cash_drawer_pin=5,
                cash_drawer_on_ms=120,
                cash_drawer_off_ms=400,
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    settings = resp.json()["settings"]
    assert settings["cash_drawer_enabled"] is True
    assert settings["cash_drawer_pin"] == 5
    assert settings["cash_drawer_on_ms"] == 120
    assert settings["cash_drawer_off_ms"] == 400


def test_drawer_requires_escpos_driver(admin_client, restaurant):
    """No driver grafico do Windows os bytes do pulso nao sao comando nenhum:
    sairiam impressos no papel."""
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant, driver_type="browser", cash_drawer_enabled=True)),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "cash_drawer_enabled" in resp.json()["error"]["message"]


def test_drawer_pulse_is_capped_at_the_command_limit(admin_client, restaurant):
    """`t1` e `t2` tem um byte cada, contado em passos de 2 ms: 510 ms e o teto
    do proprio comando, nao uma politica nossa."""
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant, cash_drawer_enabled=True, cash_drawer_on_ms=800)),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "cash_drawer_on_ms" in resp.json()["error"]["message"]


def test_drawer_off_time_cannot_be_shorter_than_the_pulse(admin_client, restaurant):
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(
            _payload(
                restaurant,
                cash_drawer_enabled=True,
                cash_drawer_on_ms=300,
                cash_drawer_off_ms=100,
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "cash_drawer_off_ms" in resp.json()["error"]["message"]


def test_printer_payload_carrega_a_gaveta(account, restaurant, branch):
    """O dicionario que a rota do recibo devolve precisa dizer que ha gaveta.

    `printer_payload` e montado a mao, e nao pelo serializer: todo campo novo
    da impressora precisa ser lembrado ali. A gaveta ja nasceu esquecida uma
    vez — o cupom da venda em dinheiro saia normalmente, o PDV recebia a
    impressora sem `cash_drawer_enabled` e o pulso nunca chegava a ser
    montado. Nada falhava; a gaveta so nao abria.
    """
    from apps.printers.models import Printer
    from apps.printers.services import printer_payload

    impressora = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Caixa 01",
        driver_type=Printer.DRIVER_ESCPOS,
        connection_type=Printer.CONNECTION_NETWORK,
        host="192.168.10.50",
        port=9100,
        cash_drawer_enabled=True,
        cash_drawer_pin=Printer.DRAWER_PIN_5,
        cash_drawer_on_ms=120,
        cash_drawer_off_ms=480,
    )

    payload = printer_payload(impressora)

    assert payload["cash_drawer_enabled"] is True
    assert payload["cash_drawer_pin"] == 5
    assert payload["cash_drawer_on_ms"] == 120
    assert payload["cash_drawer_off_ms"] == 480
