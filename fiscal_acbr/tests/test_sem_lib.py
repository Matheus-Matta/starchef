"""Sem a libacbrnfe64.so o comunicador fica DE PÉ e explica — sem simular.

Antes ele nem subia: no compose da loja, com `restart: unless-stopped`, isso
era um container reiniciando em laço e o caixa recebendo "comunicador fora do
ar", o que leva a nota para a contingência — que também precisa da lib. A
providência real (copiar a lib) não aparecia em lugar nenhum.

Simular continua proibido sem pedido explícito: uma loja "emitindo" notas que
nunca existiram na SEFAZ é pior do que nota nenhuma.
"""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def sem_lib(monkeypatch, tmp_path):
    monkeypatch.delenv("ACBR_SIMULADOR", raising=False)
    monkeypatch.setenv("ACBR_LIB_PATH", str(tmp_path / "libacbrnfe64.so"))
    monkeypatch.setenv("ACBRLIB_TOKEN", "t")
    import app.main

    cliente = TestClient(importlib.reload(app.main).app)
    cliente.headers["Authorization"] = "Bearer t"
    return cliente


def test_sobe_e_o_health_acusa_a_lib_ausente(sem_lib):
    resposta = sem_lib.get("/health")

    assert resposta.status_code == 503  # o Docker marca unhealthy, sem reiniciar
    assert resposta.json()["lib"] is False
    assert resposta.json()["simulador"] is False


def test_emitir_responde_configuracao_com_a_providencia(sem_lib):
    resposta = sem_lib.post("/v1/nfe/emitir", json={
        "uf": "SP", "cnpj": "11222333000181", "ambiente": "2", "modelo": "65",
        "tp_emis": "1", "ini": "[Identificacao]\nnNF=1\n"})

    assert resposta.json()["erro"] == "configuracao"
    assert "libacbrnfe64.so" in resposta.json()["mensagem"]
