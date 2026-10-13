"""Quanto cada requisição custou no servidor, e em quê.

O caixa via 10 s para finalizar e não havia como dizer de onde vinham: CPU
do Python, banco ou o caminho até o servidor. O cabeçalho `Server-Timing`
responde por requisição, e a lenta também vai para o log.
"""
import logging

import pytest

pytestmark = pytest.mark.django_db


def test_toda_resposta_diz_quanto_foi_banco_e_quanto_foi_aplicacao(client):
    resposta = client.get("/health/")

    tempo = resposta["Server-Timing"]
    assert "app;dur=" in tempo and "db;dur=" in tempo and "total;dur=" in tempo
    assert 'desc="0 consultas"' in tempo


def test_requisicao_lenta_vai_para_o_log(client, settings, caplog):
    settings.REQUISICAO_LENTA_MS = 0

    with caplog.at_level(logging.WARNING, logger="starchef.tempo"):
        client.get("/health/")

    assert any("requisicao lenta GET /health/" in r.getMessage() for r in caplog.records)


def test_requisicao_rapida_nao_enche_o_log(client, settings, caplog):
    settings.REQUISICAO_LENTA_MS = 60_000

    with caplog.at_level(logging.WARNING, logger="starchef.tempo"):
        client.get("/health/")

    assert not [r for r in caplog.records if r.name == "starchef.tempo"]
