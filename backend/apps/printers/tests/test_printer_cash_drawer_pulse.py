"""Os tempos e a saida do pulso `ESC p m t1 t2`.

Sao cadastro do EQUIPAMENTO, e nao um detalhe do momento em que a gaveta abre:
`t1` e `t2` tem um byte cada, contado em passos de 2 ms, e o pino e o numero
escrito no conector RJ12. Os limites daqui sao do proprio comando ESC/POS, nao
uma politica nossa.
"""
import json

import pytest

from apps.printers.tests.cash_drawer import printer_payload_body as _payload

pytestmark = pytest.mark.django_db


def test_drawer_uses_the_pulse_confirmed_on_the_real_printer(admin_client, restaurant):
    """50/500 ms viram exatamente ESC p 0 25 250 no protocolo ESC/POS."""
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant)),
        content_type="application/json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["cash_drawer_on_ms"] == 50
    assert resp.json()["cash_drawer_off_ms"] == 500


def test_drawer_settings_are_mirrored_into_settings(admin_client, restaurant):
    """O PDV guarda uma copia do cadastro junto do cupom na fila local e le os
    dois niveis — como ja faz com host, porta e timeout."""
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(
            _payload(
                restaurant,
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


def test_drawer_pulse_is_capped_at_the_command_limit(admin_client, restaurant):
    """`t1` e `t2` tem um byte cada, contado em passos de 2 ms: 510 ms e o teto
    do proprio comando, nao uma politica nossa."""
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant, cash_drawer_on_ms=800)),
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
                cash_drawer_on_ms=300,
                cash_drawer_off_ms=100,
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "cash_drawer_off_ms" in resp.json()["error"]["message"]


def test_os_tempos_sao_conferidos_mesmo_fora_do_escpos(admin_client, restaurant):
    """Os tempos sao cadastro do equipamento, nao um detalhe do pulso.

    Guardar um valor impossivel numa impressora de driver grafico so adiaria o
    problema para o dia em que alguem trocasse o driver para ESC/POS.
    """
    resp = admin_client.post(
        "/api/v1/printers/",
        json.dumps(_payload(restaurant, driver_type="browser", cash_drawer_on_ms=800)),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "cash_drawer_on_ms" in resp.json()["error"]["message"]
