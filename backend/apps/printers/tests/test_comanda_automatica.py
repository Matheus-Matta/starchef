"""Comanda automática: a balança lança na próxima comanda livre, em ordem.

As três regras que estes testes seguram são de dinheiro: pular número deixa
cartão sem uso e confunde o caixa; dois pratos no mesmo número cobram de um
cliente o almoço do outro; e sem voltar ao início a fila trava no último.
"""
import uuid

import pytest

from apps.core.tenant import tenant_context
from apps.orders.command_items import launch_item
from apps.printers import fila_da_comanda
from apps.printers.models import Scale
from apps.printers.models_fila import FilaDaComanda

pytestmark = pytest.mark.django_db


def _pesar(client, balanca, **extra):
    return client.post(
        f"/api/v1/scales/{balanca.id}/checkout-command/",
        {"comanda_automatica": True, "weight_kg": "0.400", "print": True, **extra},
        format="json",
    )


def _numero(resposta):
    assert resposta.status_code == 201, resposta.data
    return resposta.data["command"]["number"]


def test_lanca_em_ordem_crescente_sem_pular_numero(admin_client, balanca, comandas):
    assert [_numero(_pesar(admin_client, balanca)) for _ in range(3)] == [1, 2, 3]


def test_pula_so_a_comanda_ocupada(admin_client, balanca, comandas, account, manager_user):
    with tenant_context(account):
        launch_item(command=comandas[1], product=balanca.product, user=manager_user, quantity=1)

    assert [_numero(_pesar(admin_client, balanca)) for _ in range(2)] == [1, 3]


def test_depois_do_ultimo_volta_ao_inicio(admin_client, balanca, comandas, restaurant):
    """O 3 é o último: a próxima é o 1 de novo (ele foi pago e está livre)."""
    FilaDaComanda.objects.create(restaurant=restaurant, ultimo_numero=3)

    assert _numero(_pesar(admin_client, balanca)) == 1


def test_todas_em_uso_responde_409_e_nao_400(admin_client, balanca, comandas):
    """409 é estado: com 400 o PDV reenviaria a pesagem para sempre."""
    for _ in range(3):
        _numero(_pesar(admin_client, balanca))

    resposta = _pesar(admin_client, balanca)

    assert resposta.status_code == 409


def test_pesagem_que_falhou_nao_gasta_o_numero(admin_client, balanca, comandas, restaurant):
    """Sem impressora a pesagem volta atrás — e o número 1 continua sendo o próximo."""
    impressora = balanca.printer
    Scale.all_objects.filter(pk=balanca.pk).update(printer=None)
    assert _pesar(admin_client, balanca).status_code == 400
    Scale.all_objects.filter(pk=balanca.pk).update(printer=impressora)

    assert _numero(_pesar(admin_client, balanca)) == 1


def test_reenvio_da_mesma_pesagem_fica_na_mesma_comanda(admin_client, balanca, comandas):
    pesagem = str(uuid.uuid4())
    primeira = _numero(_pesar(admin_client, balanca, id=pesagem))

    reenvio = _pesar(admin_client, balanca, id=pesagem)

    assert reenvio.status_code == 200
    assert reenvio.data["command"]["number"] == primeira
    assert _numero(_pesar(admin_client, balanca)) == 2


def test_comanda_ocupada_depois_da_consulta_e_relida_sob_lock(
    admin_client, balanca, comandas, account, manager_user, monkeypatch
):
    """Outra balança (ou o garçom) anotou no 1 entre a consulta e o lock.

    A lista de candidatas ainda diz "1 livre"; só a releitura depois da trava
    percebe — sem ela, dois pratos iam para o mesmo número.
    """
    original = fila_da_comanda._candidatas

    def candidatas_com_corrida(restaurant, depois_de):
        lista = original(restaurant, depois_de)
        with tenant_context(account):
            launch_item(command=comandas[0], product=balanca.product, user=manager_user, quantity=1)
        return lista

    monkeypatch.setattr(fila_da_comanda, "_candidatas", candidatas_com_corrida)

    assert _numero(_pesar(admin_client, balanca)) == 2
