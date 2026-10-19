"""A NFC-e com a SEFAZ lenta, no Postgres de verdade (trava de linha e commit).

No SQLite a trava do pedido não existe do mesmo jeito: a corrida que deixava
a venda sem DANFE só aparece aqui. Rodar com `--ds=config.settings.test_postgres`
(ver o módulo); no SQLite estes testes são pulados.
"""
import threading
import time
from unittest import mock

import pytest
from django.db import connection

from apps.invoices.models import Invoice
from apps.invoices.providers import FiscalProvider, register_provider
from apps.invoices.tasks import emitir_nota_do_pedido_pago_task
from apps.orders.tests.nota_da_venda import URL_NOTA, URL_VENDA, ligar_nota, notas_do, venda

pytestmark = pytest.mark.django_db(transaction=True)

ENFILEIRAR = "apps.invoices.tasks.emitir_nota_do_pedido_pago_task.delay"
na_sefaz = threading.Event()


@register_provider
class _SefazLenta(FiscalProvider):
    """Autoriza, mas demora — segurando a trava do pedido, como o ACBr."""

    name = "test_sefaz_lenta"
    transmits = True
    demora = 2.0

    def emit(self, invoice, config):
        na_sefaz.set()
        time.sleep(self.demora)
        invoice.provider = self.name
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000009"
        return invoice


@pytest.fixture(autouse=True)
def so_no_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("A trava do pedido só é real no Postgres.")
    na_sefaz.clear()


@pytest.fixture
def loja(api_client, contexto_tenant, sem_caixa_obrigatorio, account, restaurant, branch):
    ligar_nota(account, restaurant, branch, provider=_SefazLenta.name)
    return api_client


def test_concluir_responde_sem_esperar_a_sefaz(loja, restaurant, produto, dinheiro, manager_user):
    """Antes, o "Concluir" durava a SEFAZ inteira; passando de 20 s, o PDV
    desistia, repetia e saía da tela. Aqui a SEFAZ leva 2 s e o Concluir não."""
    corpo = venda(restaurant, produto, dinheiro)
    with mock.patch(ENFILEIRAR) as enfileirar:
        inicio = time.monotonic()
        resposta = loja.post(URL_VENDA, corpo, format="json")
        duracao = time.monotonic() - inicio

    assert resposta.status_code == 201, resposta.content
    assert duracao < _SefazLenta.demora, f"o Concluir esperou a SEFAZ ({duracao:.1f} s)"
    enfileirar.assert_called_once()

    # O worker pega a tarefa depois: a nota sai, autorizada, uma só.
    emitir_nota_do_pedido_pago_task(*enfileirar.call_args.args)
    assert notas_do(corpo["id"]).get().status == Invoice.STATUS_ISSUED


def test_pdv_pede_a_nota_enquanto_a_automatica_esta_na_sefaz(
    loja, restaurant, produto, dinheiro, manager_user
):
    """O defeito da loja, reproduzido com a trava de verdade.

    A emissão automática está na SEFAZ segurando o pedido. O PDV pede a nota:
    a conferência "já tem nota?" ainda não a enxerga (não houve commit), a
    emissão do PDV espera a trava, e quando entra a nota já existe. Antes: 400
    "Pedido já possui nota fiscal emitida" e nenhum DANFE. Agora: a nota.
    """
    corpo = venda(restaurant, produto, dinheiro)
    with mock.patch(ENFILEIRAR):
        assert loja.post(URL_VENDA, corpo, format="json").status_code == 201

    def automatica():
        try:
            emitir_nota_do_pedido_pago_task(corpo["id"], str(manager_user.pk), False)
        finally:
            connection.close()

    fila = threading.Thread(target=automatica)
    fila.start()
    assert na_sefaz.wait(10), "a emissão automática não chegou à SEFAZ"
    resposta = loja.post(URL_NOTA, {"order": corpo["id"]}, format="json")
    fila.join(15)

    assert resposta.status_code == 200, resposta.content
    nota = notas_do(corpo["id"]).get()
    assert resposta.data["id"] == str(nota.id)
    assert resposta.data["printable"] is True


def test_dois_caixas_concluem_juntos_e_cada_nota_tem_o_seu_numero(
    loja, restaurant, produto, dinheiro, manager_user
):
    """Dois caixas fecham venda no mesmo segundo e as duas notas vão para a
    fila juntas: a numeração da série não pode repetir nem pular."""
    corpos = [venda(restaurant, produto, dinheiro) for _ in range(2)]
    with mock.patch(ENFILEIRAR):
        for corpo in corpos:
            assert loja.post(URL_VENDA, corpo, format="json").status_code == 201

    def worker(corpo):
        try:
            emitir_nota_do_pedido_pago_task(corpo["id"], str(manager_user.pk), False)
        finally:
            connection.close()

    linhas = [threading.Thread(target=worker, args=(c,)) for c in corpos]
    for linha in linhas:
        linha.start()
    for linha in linhas:
        linha.join(20)

    numeros = sorted(int(n.number) for n in Invoice.all_objects.filter(
        order_id__in=[c["id"] for c in corpos]))
    assert numeros == [1, 2]
