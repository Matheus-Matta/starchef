"""Antes do dia (previsão e aviso de véspera) e o cadastro pelo painel."""
from datetime import date
from decimal import Decimal

import pytest

from apps.cardapio_consumo.models import CardapioConsumo
from apps.cardapio_consumo.previsao import avisar_faltas_de_amanha
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db
URL = "/api/v1/stock/consumption-menus/"


def test_vespera_avisa_quanto_vai_faltar_e_para_qual_cardapio(cardapio, insumo, estoque, manager_user):
    """O dono quer saber ANTES: "faltam 3 kg de arroz para o buffet de terça"."""
    arroz = insumo("Arroz")
    estoque(arroz, 6)
    cardapio([(arroz, 5)], nome="Buffet de terça", frequencia=CardapioConsumo.SEMANAL, dias_da_semana=[1])
    cardapio([(arroz, 4)], nome="Base diária")

    assert avisar_faltas_de_amanha(hoje=date(2026, 11, 9)) == 1  # amanhã é terça

    aviso = Notification.all_objects.get(recipient=manager_user)
    assert aviso.title == "Vai faltar estoque amanhã (terça, 10/11)"
    assert "3 kg de Arroz (Base diária, Buffet de terça)" in aviso.body


def test_vespera_fica_quieta_quando_o_saldo_cobre(cardapio, insumo, estoque):
    arroz = insumo("Arroz")
    estoque(arroz, 50)
    cardapio([(arroz, 5)])

    assert avisar_faltas_de_amanha(hoje=date(2026, 11, 9)) == 0


def test_vespera_nao_sai_da_loja_ligada_a_nuvem(cardapio, insumo, estoque, settings):
    """O aviso é da nuvem: saindo dos dois lados, o gerente recebia dois."""
    settings.SYNC_ENABLED, settings.SYNC_NODE_TYPE = True, "local"
    arroz = insumo("Arroz")
    estoque(arroz, 1)
    cardapio([(arroz, 5)])

    assert avisar_faltas_de_amanha(hoje=date(2026, 11, 9)) == 0


def test_executar_agora_na_loja_e_recusado_e_a_tela_sabe(api_client, cardapio, insumo, estoque, settings):
    """Executar na loja criaria uma baixa que a nuvem também faria às 06:00."""
    settings.SYNC_ENABLED, settings.SYNC_NODE_TYPE = True, "local"
    arroz = insumo("Arroz")
    estoque(arroz, 20)
    buffet = cardapio([(arroz, 8)], confirma_sozinho=True)

    assert api_client.get(f"{URL}{buffet.pk}/previsao/").data["baixa_aqui"] is False
    resposta = api_client.post(f"{URL}{buffet.pk}/executar/")
    assert resposta.status_code == 409
    assert "nuvem" in resposta.json()["error"]["message"]


def test_cadastro_pelo_painel_com_itens_e_proximas_datas(api_client, cozinha, insumo):
    arroz = insumo("Arroz")
    resposta = api_client.post(URL, {
        "nome": "Buffet de segunda", "frequencia": "weekly", "dias_da_semana": [0], "local": str(cozinha.pk),
        "confirma_sozinho": True, "comeca_em": "2026-11-01",
        "itens": [{"ingredient": str(arroz.pk), "quantidade": "8", "unidade": "kg"}],
    }, format="json")

    assert resposta.status_code == 201, resposta.content
    assert resposta.data["itens"][0]["nome"] == "Arroz"
    assert len(resposta.data["proximas_datas"]) == 3
    assert CardapioConsumo.all_objects.get().restaurant_id == cozinha.restaurant_id


@pytest.mark.parametrize("campos, erro", [
    ({"frequencia": "weekly", "dias_da_semana": []}, "dias_da_semana"),
    ({"frequencia": "monthly"}, "dia_do_mes"),
    ({"itens": []}, "itens"),
])
def test_cadastro_incompleto_e_recusado_com_o_campo(api_client, cozinha, insumo, campos, erro):
    arroz = insumo("Arroz")
    corpo = {"nome": "X", "local": str(cozinha.pk),
             "itens": [{"ingredient": str(arroz.pk), "quantidade": "1"}], **campos}
    resposta = api_client.post(URL, corpo, format="json")
    assert resposta.status_code == 400 and erro in str(resposta.content)


def test_unidade_que_nao_converte_e_recusada(api_client, cozinha, insumo):
    """1 'un' de arroz em kg não tem conversão: a baixa diária ia pular a linha calada."""
    arroz = insumo("Arroz")
    resposta = api_client.post(URL, {"nome": "X", "local": str(cozinha.pk), "itens": [
        {"ingredient": str(arroz.pk), "quantidade": "1", "unidade": "un"}]}, format="json")
    assert resposta.status_code == 400 and "não converte" in str(resposta.json()["error"]["message"])


def test_previsao_e_executar_agora_pelo_painel(api_client, cardapio, insumo, estoque):
    arroz = insumo("Arroz")
    estoque(arroz, 5)
    buffet = cardapio([(arroz, 8)], confirma_sozinho=True)

    previsao = api_client.get(f"{URL}{buffet.pk}/previsao/").data
    assert previsao["linhas"][0]["falta"] == "3.000" and previsao["baixa_aqui"] is True

    assert api_client.post(f"{URL}{buffet.pk}/executar/").status_code == 201
    assert api_client.post(f"{URL}{buffet.pk}/executar/").status_code == 409
    historico = api_client.get(f"{URL}{buffet.pk}/historico/").data
    assert historico[0]["situacao"] == "posted" and Decimal(historico[0]["faltas"][0]["faltou"]) == 3
