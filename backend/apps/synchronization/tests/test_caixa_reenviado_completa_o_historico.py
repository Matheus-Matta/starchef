"""O histórico do caixa que não chegou à nuvem: achar onde parou e mandar de novo.

O fechamento chega (a sessão é uma linha só, com o esperado e o contado), mas
suprimento, sangria, venda em dinheiro e troco são linhas à parte, cada uma com
o seu evento. Um movimento preso na fila — esperando um pai que não chegou,
virado conflito, descartado — some do extrato da nuvem sem mudar o valor final.

`manage.py sync_caixa` responde as duas perguntas: onde cada evento do caixa
parou neste servidor, e (na loja, com `--reenviar`) gerar de novo os eventos
das sessões, para a nuvem completar o que falta. Reenviar é seguro: o que a
nuvem já tem chega com a mesma versão e é ignorado.
"""
import uuid
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import PaymentMethod
from apps.payments.services import (
    approve_cash_operation, close_cash_register, create_cash_movement, open_cash_register, register_payment,
)
from apps.synchronization.constants import Direction, EventStatus
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import caixa_diagnostico

pytestmark = pytest.mark.django_db


@pytest.fixture
def turno(como_loja, account, restaurant, branch, admin_user):
    with tenant_context(account):
        sessao = open_cash_register(restaurant=restaurant, branch=branch, user=admin_user,
                                    opening_amount=Decimal("100"))
        produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch, name="P",
                                         internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("21.50"))
        dinheiro = PaymentMethod.objects.create(account=account, restaurant=restaurant, branch=branch,
                                                name="Dinheiro", method_type=PaymentMethod.TYPE_CASH)
        pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=admin_user)
        add_order_item(order=pedido, product=produto, quantity=2, user=admin_user)
        pedido.refresh_from_db()
        register_payment(order=pedido, user=admin_user, payment_method_id=dinheiro.pk, amount=Decimal("50"),
                         cash_register_id=sessao.pk)
        suprimento = create_cash_movement(cash_register=sessao, user=admin_user, movement_type="supply",
                                          amount="20", reason="")
        approve_cash_operation(cash_register=sessao, user=admin_user, reason="ok", movement=suprimento)
        close_cash_register(cash_register=sessao, user=admin_user, actual_amount=Decimal("163"))
    return sessao


def _saida():
    return list(SyncEvent.objects.filter(direction=Direction.OUTBOUND).order_by("sequence"))


def test_reenviar_gera_de_novo_sessao_pedido_recebimento_e_movimentos(turno):
    SyncEvent.objects.all().delete()  # o que se perdeu no caminho

    total = caixa_diagnostico.reenviar(dias=7)

    tipos = [e.entity_type for e in _saida()]
    assert total == len(tipos)
    assert tipos.count("cash_movement") == 4  # abertura, venda, suprimento, fechamento
    assert {"cash_register", "order", "order_item", "payment"} <= set(tipos)
    # A ordem que o destino precisa: a sessão antes dos movimentos, o pedido
    # antes do recebimento, o recebimento antes da venda em dinheiro.
    assert tipos.index("cash_register") < tipos.index("cash_movement")
    assert tipos.index("order") < tipos.index("payment")


def test_reenviar_so_roda_na_loja(como_nuvem):
    with pytest.raises(caixa_diagnostico.SoNaLoja):
        caixa_diagnostico.reenviar(dias=7)


def test_diagnostico_mostra_o_evento_parado_e_o_motivo(turno):
    parado = SyncEvent.objects.filter(entity_type="cash_movement").first()
    parado.status = EventStatus.FAILED
    parado.last_error = "CashMovement.payment aponta para Payment X, que ainda não existe aqui."
    parado.save(update_fields=["status", "last_error"])

    saida = StringIO()
    call_command("sync_caixa", "--dias", "7", stdout=saida)

    texto = saida.getvalue()
    assert "cash_movement" in texto
    assert "FAILED" in texto
    assert "ainda não existe aqui" in texto
