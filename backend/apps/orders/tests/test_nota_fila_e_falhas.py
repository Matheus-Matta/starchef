"""A NFC-e em segundo plano quando o que falha não é o operador.

A fila do Celery cai no meio do turno, o worker reinicia e entrega a mesma
tarefa duas vezes, o pedido some antes de a fila rodar, a SEFAZ recusa. Em
nenhum caso a venda paga pode ficar sem nota, com duas notas, ou com a recusa
escondida atrás de "a nota que já existe".
"""
import uuid
from unittest import mock

import pytest
from kombu.exceptions import OperationalError

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FiscalProvider, FiscalRejection, register_provider
from apps.invoices.tasks import emitir_nota_do_pedido_pago_task
from apps.orders.tests.nota_da_venda import notas_do, venda

pytestmark = pytest.mark.django_db

ENFILEIRAR = "apps.invoices.tasks.emitir_nota_do_pedido_pago_task.delay"


@register_provider
class _SefazRecusa(FiscalProvider):
    """Cadastro tributário errado: a SEFAZ recusa toda nota."""

    name = "test_sefaz_recusa"
    transmits = True

    def emit(self, invoice, config):
        raise FiscalRejection("Rejeicao 778: NCM inexistente (simulado)")


def test_redis_fora_no_meio_do_turno_cada_venda_ganha_a_sua_nota(
    caixa, restaurant, produto, dinheiro
):
    """Sem a fila, a nota volta a sair na própria requisição — mais lenta, mas
    nenhuma venda fica sem nota e a numeração segue em ordem."""
    corpos = [venda(restaurant, produto, dinheiro) for _ in range(3)]

    with mock.patch(ENFILEIRAR, side_effect=OperationalError("redis fora")):
        respostas = [caixa.concluir(corpo) for corpo in corpos]

    assert [r.status_code for r in respostas] == [201, 201, 201]
    numeros = sorted(int(n.number) for n in Invoice.all_objects.filter(
        order_id__in=[c["id"] for c in corpos]))
    assert numeros == [1, 2, 3]


def test_tarefa_entregue_duas_vezes_nao_faz_segunda_nota(
    caixa, restaurant, produto, dinheiro, manager_user
):
    """O worker caiu depois de emitir e o Celery entregou a tarefa de novo."""
    corpo = venda(restaurant, produto, dinheiro)
    with mock.patch(ENFILEIRAR):
        caixa.concluir(corpo)

    primeira = emitir_nota_do_pedido_pago_task(corpo["id"], str(manager_user.pk), False)
    segunda = emitir_nota_do_pedido_pago_task(corpo["id"], str(manager_user.pk), False)

    assert primeira is True and segunda is True
    assert notas_do(corpo["id"]).count() == 1
    caixa.config.refresh_from_db()
    assert caixa.config.next_number == 2


def test_fila_que_roda_depois_do_pdv_ja_ter_emitido_nao_duplica(
    caixa, restaurant, produto, dinheiro, manager_user
):
    """Ordem invertida: o PDV pediu a nota antes de a fila chegar à tarefa."""
    corpo = venda(restaurant, produto, dinheiro)
    with mock.patch(ENFILEIRAR):
        caixa.concluir(corpo)
    pelo_pdv = caixa.pedir_nota(corpo["id"])

    emitir_nota_do_pedido_pago_task(corpo["id"], str(manager_user.pk), False)

    assert pelo_pdv.status_code == 201, pelo_pdv.content
    assert notas_do(corpo["id"]).count() == 1


def test_tarefa_de_pedido_que_nao_existe_mais_termina_sem_erro(caixa):
    """O pedido foi apagado (ou é de outro nó) antes de a fila rodar."""
    assert emitir_nota_do_pedido_pago_task(str(uuid.uuid4()), None, True) is False


def test_tarefa_sem_usuario_ainda_emite(caixa, restaurant, produto, dinheiro):
    """Venda que chegou pela sincronização: não há operador para atribuir."""
    corpo = venda(restaurant, produto, dinheiro)
    with mock.patch(ENFILEIRAR):
        caixa.concluir(corpo)

    assert emitir_nota_do_pedido_pago_task(corpo["id"], None, True) is True
    assert notas_do(corpo["id"]).count() == 1


def test_recusa_da_sefaz_chega_ao_pdv_e_nao_vira_nota_que_ja_existe(
    caixa, restaurant, produto, dinheiro
):
    """A nota recusada fica gravada em erro. O PDV que pede de novo precisa
    VER a recusa (e o motivo), não um "a nota já existe" que manda imprimir um
    documento que a SEFAZ nunca autorizou."""
    FiscalConfig.all_objects.filter(pk=caixa.config.pk).update(provider=_SefazRecusa.name)
    corpo = venda(restaurant, produto, dinheiro)
    caixa.concluir(corpo)
    assert notas_do(corpo["id"]).get().status == Invoice.STATUS_ERROR

    resposta = caixa.pedir_nota(corpo["id"])

    assert resposta.status_code == 201, resposta.content
    assert resposta.data["printable"] is False
    assert resposta.data["fiscal_state"] == "rejected"
    assert "778" in (resposta.data.get("error_message") or "")
    assert notas_do(corpo["id"]).count() == 1
