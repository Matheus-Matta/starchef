"""Toda falha da emissão deixa a NOTA gravada com o erro — para reenviar depois.

A recusa da SEFAZ e o cadastro incompleto já ficavam na nota. Mas o que
falhava ANTES de montá-la — pedido sem item faturável, CPF/CNPJ inválido,
qualquer exceção no meio da montagem — só devolvia um 400/500 e nada era
gravado: a venda paga ficava sem nota e sem registro de que deveria ter tido
uma, e não havia o que reenviar depois de corrigir.
"""
import pytest

from apps.invoices.models import Invoice
from apps.invoices.services import emit_fiscal_invoice, resend_fiscal_invoice
from apps.invoices.tests.test_acbrlib_provider import Comunicador, ambiente  # noqa: F401
from apps.orders.models import OrderItem

pytestmark = pytest.mark.django_db


@pytest.fixture
def comunicador(monkeypatch):
    falso = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", falso)
    return falso


def _itens(pedido, status):
    # `all_objects`: fora do contexto da conta o `objects` não vê linha nenhuma.
    assert OrderItem.all_objects.filter(order=pedido).update(status=status)


def test_pedido_sem_item_faturavel_grava_a_nota_com_erro(ambiente, comunicador):  # noqa: F811
    _itens(ambiente.pedido, OrderItem.STATUS_CANCELLED)
    numero_antes = ambiente.config.next_number

    nota = emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)

    assert nota.status == Invoice.STATUS_ERROR
    assert "sem itens faturaveis" in nota.error_message.lower()
    assert Invoice.all_objects.filter(order=ambiente.pedido).count() == 1
    assert comunicador.chamadas == []
    ambiente.config.refresh_from_db()
    assert ambiente.config.next_number == numero_antes  # número não gasto


def test_corrigido_o_pedido_o_reenvio_emite_a_mesma_nota(ambiente, comunicador):  # noqa: F811
    _itens(ambiente.pedido, OrderItem.STATUS_CANCELLED)
    nota = emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)
    _itens(ambiente.pedido, OrderItem.STATUS_PENDING)  # o item volta

    reenviada = resend_fiscal_invoice(nota, user=ambiente.user)

    assert reenviada.pk == nota.pk
    assert reenviada.status == Invoice.STATUS_ISSUED
    assert reenviada.number
    assert Invoice.all_objects.filter(order=ambiente.pedido).count() == 1


def test_cpf_invalido_grava_o_erro_e_emitir_de_novo_com_o_certo_aproveita_a_nota(
    ambiente, comunicador  # noqa: F811
):
    nota = emit_fiscal_invoice(ambiente.pedido, user=ambiente.user, cpf="11111111111")

    assert nota.status == Invoice.STATUS_ERROR
    assert "CPF" in nota.error_message

    corrigida = emit_fiscal_invoice(ambiente.pedido, user=ambiente.user, cpf="52998224725")

    assert corrigida.pk == nota.pk
    assert corrigida.status == Invoice.STATUS_ISSUED
    assert corrigida.recipient_cpf == "52998224725"


def test_excecao_no_meio_da_montagem_grava_a_nota_com_erro(ambiente, comunicador, monkeypatch):  # noqa: F811
    def quebra(*_a, **_k):
        raise RuntimeError("perfil fiscal corrompido")

    monkeypatch.setattr("apps.invoices.services.rebuild_invoice_items", quebra)
    numero_antes = ambiente.config.next_number

    nota = emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)

    assert nota.status == Invoice.STATUS_ERROR
    assert "perfil fiscal corrompido" in nota.error_message
    assert Invoice.all_objects.filter(order=ambiente.pedido).count() == 1
    ambiente.config.refresh_from_db()
    assert ambiente.config.next_number == numero_antes


def test_a_api_devolve_a_nota_com_erro_e_nao_um_400(api_client, ambiente, comunicador):  # noqa: F811
    conta = ambiente.pedido.account
    conta.enabled_modules = ["financeiro"]  # a emissão é do módulo financeiro
    conta.save(update_fields=["enabled_modules"])
    _itens(ambiente.pedido, OrderItem.STATUS_CANCELLED)

    resposta = api_client.post("/api/v1/invoices/emit/", {"order": str(ambiente.pedido.pk)},
                               format="json")

    assert resposta.status_code == 201, resposta.content
    assert resposta.json()["status"] == Invoice.STATUS_ERROR
    assert resposta.json()["fiscal_state"] != "issued"
