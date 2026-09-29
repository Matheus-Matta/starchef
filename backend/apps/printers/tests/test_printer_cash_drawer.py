"""A gaveta segue o driver, e nao uma caixa que alguem marca.

Nao ha um "tem gaveta?" a cadastrar. Quem recebe o comando e a IMPRESSORA, que
energiza a saida do conector — ela nao tem como saber se ha uma gaveta do outro
lado do cabo. Por isso `cash_drawer_enabled` e o espelho de `driver_type`.

Os tempos e o pino do pulso estao em `test_printer_cash_drawer_pulse.py`; o que
o PDV recebe, em `test_printer_cash_drawer_payload.py`.
"""
import json

import pytest

from apps.printers.tests.cash_drawer import printer_payload_body as _payload

pytestmark = pytest.mark.django_db


def test_drawer_follows_the_escpos_driver(admin_client, restaurant):
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant)),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["cash_drawer_enabled"] is True


def test_drawer_stays_disabled_for_non_escpos_printer(admin_client, restaurant):
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant, driver_type="browser")),
        content_type="application/json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["cash_drawer_enabled"] is False


def test_switching_away_from_escpos_disables_the_drawer(admin_client, restaurant):
    created = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant)),
        content_type="application/json",
    )

    resp = admin_client.patch(
        f"/api/v1/printers/{created.json()['id']}/",
        json.dumps({"driver_type": "browser"}),
        content_type="application/json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["cash_drawer_enabled"] is False


def test_switching_to_escpos_enables_the_drawer(admin_client, restaurant):
    """O caminho inverso, que era o defeito: a impressora nascia no driver
    grafico, virava ESC/POS depois, e a gaveta continuava desligada para
    sempre porque a tela nunca ofereceu a caixa para marcar."""
    created = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant, driver_type="browser")),
        content_type="application/json",
    )

    resp = admin_client.patch(
        f"/api/v1/printers/{created.json()['id']}/",
        json.dumps({"driver_type": "escpos"}),
        content_type="application/json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["cash_drawer_enabled"] is True


def test_drawer_cannot_be_turned_off_by_the_client(admin_client, restaurant):
    """Nao ha como desligar a gaveta de uma ESC/POS pela API.

    Era exatamente esse campo, gravado `False` e nunca oferecido em tela, que
    mantinha trancada uma gaveta perfeitamente ligada.
    """
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant, cash_drawer_enabled=False)),
        content_type="application/json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["cash_drawer_enabled"] is True
