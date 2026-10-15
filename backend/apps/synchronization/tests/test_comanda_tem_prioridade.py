"""A comanda não espera a fila: ela é o que o salão e o caixa leem AGORA.

O garçom lança na comanda pelo celular (às vezes na nuvem, com a loja fora) e
o caixa lê o cartão segundos depois, na loja. Com a sincronização normal, a
loja só sabia da novidade no próximo aviso periódico — até 10 s —, e depois de
uma queda de internet a anotação ficava atrás de centenas de eventos de
cadastro e estoque. O caixa cobrava a comanda sem o último item.

Duas regras:

1. A nuvem avisa a loja NO COMMIT de uma escrita da comanda, sem esperar o
   aviso periódico.
2. Com fila acumulada, o que é da comanda sai no primeiro lote.
"""
import pytest

from apps.restaurants.models import Command, Restaurant
from apps.synchronization.services import dispatch, prioridade

pytestmark = pytest.mark.django_db


@pytest.fixture
def avisos(monkeypatch):
    grupos = []
    monkeypatch.setattr(prioridade, "_avisar", lambda grupo: grupos.append(grupo) or True)
    return grupos


def _restaurante(conta, nome="R"):
    return Restaurant.objects.create(account=conta, legal_name=f"{nome} LTDA", trade_name=nome)


def test_escrita_da_comanda_na_nuvem_avisa_a_loja_no_commit(
    como_nuvem, conta, no_loja, avisos, django_capture_on_commit_callbacks
):
    restaurante = _restaurante(conta)
    avisos.clear()

    with django_capture_on_commit_callbacks(execute=True):
        Command.objects.create(account=conta, restaurant=restaurante, number=7)

    assert avisos == [no_loja.group_name]


def test_cadastro_comum_espera_o_aviso_periodico(
    como_nuvem, conta, avisos, django_capture_on_commit_callbacks
):
    """Prioridade para tudo é prioridade para nada: só a comanda fura a fila."""
    with django_capture_on_commit_callbacks(execute=True):
        _restaurante(conta)

    assert avisos == []


def test_varias_escritas_da_comanda_avisam_uma_vez_por_transacao(
    como_nuvem, conta, no_loja, avisos, django_capture_on_commit_callbacks
):
    restaurante = _restaurante(conta)
    avisos.clear()

    with django_capture_on_commit_callbacks(execute=True):
        for numero in (1, 2, 3):
            Command.objects.create(account=conta, restaurant=restaurante, number=numero)

    assert avisos == [no_loja.group_name]


def test_a_loja_nao_avisa_ninguem(como_loja, conta, avisos, django_capture_on_commit_callbacks):
    """Quem disca é a loja: ela não tem grupo de canal para avisar a nuvem."""
    restaurante = _restaurante(conta)

    with django_capture_on_commit_callbacks(execute=True):
        Command.objects.create(account=conta, restaurant=restaurante, number=9)

    assert avisos == []


def test_com_fila_acumulada_a_comanda_sai_no_primeiro_lote(
    como_nuvem, conta, no_nuvem, no_loja, settings, avisos
):
    settings.SYNC_BATCH_MAX_EVENTS = 3
    for i in range(6):  # a fila que se acumulou durante a queda
        restaurante = _restaurante(conta, f"R{i}")
    Command.objects.create(account=conta, restaurant=restaurante, number=11)

    lote, _bytes = dispatch.collect_batch(no_nuvem, no_loja)

    tipos = [e.entity_type for e in lote]
    assert tipos[0] == "command", tipos
    assert len(lote) == 3


def test_sem_comanda_na_fila_a_ordem_continua_a_da_sequencia(como_nuvem, conta, no_nuvem, no_loja, avisos):
    for i in range(3):
        _restaurante(conta, f"S{i}")

    lote, _bytes = dispatch.collect_batch(no_nuvem, no_loja)

    sequencias = [e.sequence for e in lote]
    assert sequencias == sorted(sequencias)
