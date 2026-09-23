"""A loja se apresenta como o ambiente em que ela REALMENTE está.

O `environment` do HELLO estava fixo em `"development"` no transporte. Ficou
certo por acidente enquanto só existia um ambiente — e no dia em que a nuvem
passou para `production`, toda loja passou a se apresentar como development.

O handshake era recusado em laço, a cada reconexão:

    sync: sessão encerrada (Ambiente incompatível: o nó declara 'development'
    e esta instalação é 'production'). Reconectando…

Nada subia. A fila só crescia, e do lado da loja o sintoma era mudo: pedidos
do dia inteiro parados sem ninguém ver, porque reconectar é comportamento
normal e o log de aviso se repete até virar paisagem.

A conferência do outro lado é legítima e continua existindo: sem ela, uma loja
de homologação entraria na nuvem de produção e gravaria venda de teste no
banco que vale. O defeito era a loja mentir sobre quem é.
"""
import pytest

from apps.synchronization.services.transport import CloudConnection


pytestmark = pytest.mark.django_db


def _transporte():
    return CloudConnection(
        url="wss://api.exemplo/ws/sync/v1/",
        token="token-do-no",
        node_id="11111111-1111-4111-8111-111111111111",
        pair_id="22222222-2222-4222-8222-222222222222",
        account_id="33333333-3333-4333-8333-333333333333",
    )


@pytest.mark.parametrize("ambiente", ["development", "production"])
def test_o_hello_leva_o_ambiente_DESTA_instalacao(settings, ambiente):
    settings.SYNC_ENVIRONMENT = ambiente

    assert _transporte()._hello_payload()["environment"] == ambiente


def test_o_ambiente_NAO_e_constante_no_codigo():
    """O teste que fecha a porta por onde o defeito entrou.

    Um valor fixo passa em qualquer teste que só olhe um ambiente. Este olha
    os DOIS e falha se a resposta for a mesma nos dois — que é exatamente o
    que acontecia.
    """
    from django.test import override_settings

    with override_settings(SYNC_ENVIRONMENT="development"):
        em_dev = _transporte()._hello_payload()["environment"]
    with override_settings(SYNC_ENVIRONMENT="production"):
        em_prod = _transporte()._hello_payload()["environment"]

    assert em_dev != em_prod, (
        "o ambiente do HELLO não acompanha a instalação — está fixo no código"
    )


def test_o_resto_do_hello_continua_inteiro(settings):
    """Protocolo e esquema são o que decide compatibilidade; não podem sumir."""
    settings.SYNC_ENVIRONMENT = "production"

    payload = _transporte()._hello_payload()

    assert payload["node_id"] == "11111111-1111-4111-8111-111111111111"
    assert payload["account_id"] == "33333333-3333-4333-8333-333333333333"
    assert payload["protocol_version"]
    assert "schema_version" in payload
