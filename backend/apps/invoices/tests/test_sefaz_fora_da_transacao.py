"""A chamada à SEFAZ não acontece com transação aberta.

Antes, `emit_fiscal_invoice` era `@transaction.atomic` de ponta a ponta e a
transmissão (até 40 s na ACBrLib) rodava lá dentro: a linha da `FiscalConfig`
ficava travada a transmissão inteira — o `atomic()` interno é só um
savepoint, e savepoint não solta trava —, então toda nota do restaurante
esperava a SEFAZ da anterior. E o `/invoices/emit/` do PDV, que chega logo
depois do pagamento, parava no `select_for_update` do pedido segurando um
worker do gunicorn e uma conexão do banco. Com 5 caixas a loja travava.

Agora a nota é numerada e gravada "em andamento" num commit curto, a SEFAZ é
chamada sem transação, e o resultado é gravado em outro commit curto.
"""
import uuid
from decimal import Decimal

import pytest
from django.db import connection

from apps.core.tenant import tenant_context
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FiscalProvider, register_provider
from apps.invoices.services import (
    EM_VOO,
    emit_fiscal_invoice,
    fiscal_state_of,
)
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db

NOME = "test_sefaz_fora_da_transacao"


class _Observado:
    """O que o provedor viu no instante da transmissão."""

    savepoints = None
    no_banco = None
    durante = None  # chamado no meio da transmissão (simula o PDV)
    consultas = 0


@register_provider
class _ProvedorObservador(FiscalProvider):
    name = NOME
    transmits = True

    def emit(self, invoice, config):
        _Observado.savepoints = len(connection.savepoint_ids)
        _Observado.no_banco = Invoice.all_objects.get(pk=invoice.pk)
        if _Observado.durante:
            _Observado.durante(invoice)
        invoice.provider = self.name
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000001"
        return invoice

    def cancel(self, invoice, reason):
        invoice.status = Invoice.STATUS_CANCELLED
        return invoice

    def status(self, invoice):
        _Observado.consultas += 1
        return invoice.status


@pytest.fixture(autouse=True)
def _limpa():
    _Observado.savepoints = _Observado.no_banco = _Observado.durante = None
    _Observado.consultas = 0
    yield


@pytest.fixture
def pedido(account, restaurant, branch, manager_user):
    from apps.menu.models import Product

    with tenant_context(account):
        FiscalConfig.objects.create(
            account=account, restaurant=restaurant, branch=branch,
            document_model=FiscalConfig.MODEL_NFCE, series=1, next_number=10,
            environment="2", cnpj="63201558000155", uf="RJ", provider=NOME,
        )
        produto = Product.objects.create(
            account=account, restaurant=restaurant, branch=branch,
            name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}",
            sale_price=Decimal("25.00"),
        )
        order = create_order(
            restaurant=restaurant, branch=branch,
            order_type=Order.TYPE_COUNTER, user=manager_user,
        )
        add_order_item(order=order, product=produto, quantity=1, user=manager_user)
        yield order


def test_a_transmissao_roda_sem_transacao_aberta(pedido, manager_user):
    """Nenhum savepoint da emissão está aberto quando o provedor é chamado.

    O teste roda dentro da transação do pytest; o que importa é que a
    EMISSÃO não abriu nenhuma por cima dela — sem isso a trava da
    configuração e a do pedido ficariam presas durante a SEFAZ.
    """
    antes = len(connection.savepoint_ids)

    nota = emit_fiscal_invoice(pedido, user=manager_user)

    assert _Observado.savepoints == antes
    assert nota.status == Invoice.STATUS_ISSUED


def test_durante_a_transmissao_a_nota_ja_existe_em_andamento(pedido, manager_user):
    """Quem pedir a nota no meio recebe ESTA, e não emite outra."""
    nota = emit_fiscal_invoice(pedido, user=manager_user)

    visto = _Observado.no_banco
    assert visto.status == Invoice.STATUS_PENDING
    assert visto.number == nota.number
    assert fiscal_state_of(visto) == "processing"
    assert EM_VOO in visto.fiscal_payload
    # E a marca some quando a transmissão termina.
    nota.refresh_from_db()
    assert EM_VOO not in (nota.fiscal_payload or {})
    assert "awaiting" not in (nota.fiscal_payload or {})


def test_o_numero_fica_reservado_durante_a_transmissao(pedido, manager_user):
    """A emissão seguinte, no meio desta, não repete o número."""
    vistos = {}

    def proximo_numero(invoice):
        vistos["contador"] = FiscalConfig.all_objects.get(provider=NOME).next_number

    _Observado.durante = proximo_numero
    nota = emit_fiscal_invoice(pedido, user=manager_user)

    assert vistos["contador"] == int(nota.number) + 1


def test_a_marca_do_terminal_gravada_no_meio_sobrevive(pedido, manager_user):
    """O `/invoices/emit/` do PDV marca `terminal_prints` na nota em andamento.

    A gravação final escreve o `fiscal_payload` inteiro; sem preservar a
    marca, o agente local imprimiria uma via e o terminal outra.
    """
    def pdv_pede_a_nota(invoice):
        no_banco = Invoice.all_objects.get(pk=invoice.pk)
        Invoice.all_objects.filter(pk=invoice.pk).update(
            fiscal_payload={**no_banco.fiscal_payload, "terminal_prints": True},
        )

    _Observado.durante = pdv_pede_a_nota
    nota = emit_fiscal_invoice(pedido, user=manager_user)

    nota.refresh_from_db()
    assert nota.fiscal_payload.get("terminal_prints") is True
    assert nota.status == Invoice.STATUS_ISSUED
