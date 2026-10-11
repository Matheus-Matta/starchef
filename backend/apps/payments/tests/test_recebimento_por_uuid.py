"""O recebimento tem a identidade que o PDV deu a ele: UUID + horário.

Loja e nuvem aceitam receber (o PDV escolhe o servidor, e desvia quando um
cai). O que impede cobrar duas vezes é o DADO, não a recusa de um servidor: o
mesmo UUID enviado aos dois vira UMA linha quando a sincronização os junta,
e o reenvio no mesmo servidor devolve o que já existe. Chegou uma versão mais
velha do que a gravada? Nada muda.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.recebimento_por_uuid import RecebimentoEmConflito
from apps.payments.services import register_payment
from apps.payments.tests.test_payment_service_card_subtype import (  # noqa: F401 — fixtures
    card_method, payable_order,
)

pytestmark = pytest.mark.django_db


def _receber(pedido, metodo, usuario, pid, momento, *, subtipo="credit", valor="7.00"):
    return register_payment(
        order=pedido, user=usuario, payment_method_id=metodo.id, amount=valor,
        metadata={"card_subtype": subtipo}, payment_id=pid, client_updated_at=momento,
    )


def test_uuid_novo_cria_o_recebimento_com_esse_id(payable_order, card_method, manager_user):  # noqa: F811
    pid = uuid.uuid4()
    pagamento = _receber(payable_order, card_method, manager_user, pid, timezone.now())
    assert pagamento.pk == pid


def test_reenvio_do_mesmo_uuid_devolve_o_existente_mesmo_com_o_pedido_pago(
    payable_order, card_method, manager_user  # noqa: F811
):
    """O primeiro quitou o pedido; o reenvio não pode virar "o pedido já foi pago"."""
    pid, agora = uuid.uuid4(), timezone.now()
    primeiro = _receber(payable_order, card_method, manager_user, pid, agora)
    segundo = _receber(payable_order, card_method, manager_user, pid, agora)
    assert segundo.pk == primeiro.pk
    assert Payment.all_objects.filter(order=payable_order).count() == 1


def test_versao_mais_nova_atualiza_e_mais_velha_e_ignorada(
    payable_order, card_method, manager_user  # noqa: F811
):
    pid, agora = uuid.uuid4(), timezone.now()
    _receber(payable_order, card_method, manager_user, pid, agora, subtipo="credit")

    _receber(payable_order, card_method, manager_user, pid, agora + timedelta(seconds=5),
             subtipo="debit")
    assert Payment.all_objects.get(pk=pid).card_subtype == "debit"

    # A requisição antiga chega atrasada (fila, desvio para a nuvem): nada muda.
    _receber(payable_order, card_method, manager_user, pid, agora + timedelta(seconds=1),
             subtipo="credit")
    assert Payment.all_objects.get(pk=pid).card_subtype == "debit"
    assert Payment.all_objects.filter(order=payable_order).count() == 1


@pytest.fixture
def pix_method(account, restaurant, branch):
    from apps.payments.models import PaymentMethod

    return PaymentMethod.objects.create(account=account, restaurant=restaurant, branch=branch,
                                        name="Pix", method_type=PaymentMethod.TYPE_PIX)


def test_versao_mais_nova_muda_o_valor_na_mesma_linha_e_quita_o_pedido(
    payable_order, card_method, manager_user  # noqa: F811
):
    """O UUID é a única coisa fixa: o valor novo vale, na MESMA linha."""
    pid, agora = uuid.uuid4(), timezone.now()
    _receber(payable_order, card_method, manager_user, pid, agora, valor="5.00")
    payable_order.refresh_from_db()
    assert payable_order.payment_status == "partial"

    _receber(payable_order, card_method, manager_user, pid, agora + timedelta(seconds=5), valor="7.00")

    pagamento = Payment.all_objects.get(pk=pid)
    assert (pagamento.amount, pagamento.status) == (Decimal("7.00"), Payment.STATUS_APPROVED)
    assert Payment.all_objects.filter(order=payable_order).count() == 1
    payable_order.refresh_from_db()
    assert payable_order.payment_status == "paid"


def test_versao_mais_nova_muda_a_forma(payable_order, card_method, pix_method, manager_user):  # noqa: F811
    pid, agora = uuid.uuid4(), timezone.now()
    _receber(payable_order, card_method, manager_user, pid, agora)
    _receber(payable_order, pix_method, manager_user, pid, agora + timedelta(seconds=5), subtipo="")

    pagamento = Payment.all_objects.get(pk=pid)
    assert pagamento.payment_method_id == pix_method.id and pagamento.status == Payment.STATUS_APPROVED
    assert Payment.all_objects.filter(order=payable_order).count() == 1


def test_valor_diferente_com_horario_velho_e_ignorado(payable_order, card_method, manager_user):  # noqa: F811
    pid, agora = uuid.uuid4(), timezone.now()
    _receber(payable_order, card_method, manager_user, pid, agora, valor="5.00")
    _receber(payable_order, card_method, manager_user, pid, agora - timedelta(seconds=5), valor="2.00")
    assert Payment.all_objects.get(pk=pid).amount == Decimal("5.00")
    assert Payment.all_objects.filter(order=payable_order).count() == 1


def test_uuid_em_outro_pedido_e_conflito(payable_order, card_method, manager_user):  # noqa: F811
    from apps.orders.models import Order
    from apps.orders.services import create_order

    pid, agora = uuid.uuid4(), timezone.now()
    _receber(payable_order, card_method, manager_user, pid, agora)
    outro = create_order(restaurant=payable_order.restaurant, branch=payable_order.branch,
                         order_type=Order.TYPE_COUNTER, user=manager_user)
    with pytest.raises(RecebimentoEmConflito):
        _receber(outro, card_method, manager_user, pid, agora + timedelta(seconds=5))


def test_mudar_o_valor_com_nfce_emitida_e_conflito(payable_order, card_method, manager_user):  # noqa: F811
    from apps.invoices.models import Invoice

    pid, agora = uuid.uuid4(), timezone.now()
    _receber(payable_order, card_method, manager_user, pid, agora, valor="5.00")
    Invoice.all_objects.create(account=payable_order.account, restaurant=payable_order.restaurant,
                               branch=payable_order.branch, order=payable_order,
                               status=Invoice.STATUS_ISSUED, number="1", series=1)
    with pytest.raises(RecebimentoEmConflito):
        _receber(payable_order, card_method, manager_user, pid, agora + timedelta(seconds=5), valor="7.00")
    assert Payment.all_objects.get(pk=pid).amount == Decimal("5.00")


def test_pela_api_reenvio_devolve_o_mesmo_e_versao_nova_atualiza(
    api_client, payable_order, card_method  # noqa: F811
):
    """O caminho do PDV: `POST /pay/` com `id` e `client_updated_at` no corpo."""
    pid, agora = str(uuid.uuid4()), timezone.now()
    corpo = {"payment_method": str(card_method.id), "amount": "5.00", "id": pid,
             "client_updated_at": agora.isoformat(), "metadata": {"card_subtype": "credit"}}
    url = f"/api/v1/orders/{payable_order.id}/pay/"

    primeiro = api_client.post(url, corpo, format="json")
    reenvio = api_client.post(url, corpo, format="json")
    nova = api_client.post(url, {**corpo, "amount": "7.00",
                                 "client_updated_at": (agora + timedelta(seconds=5)).isoformat()},
                           format="json")

    assert primeiro.status_code == 201, primeiro.content
    assert reenvio.json()["id"] == pid and Decimal(reenvio.json()["amount"]) == Decimal("5.00")
    assert nova.status_code == 201, nova.content
    assert nova.json()["id"] == pid and Decimal(nova.json()["amount"]) == Decimal("7.00")
    assert Payment.all_objects.filter(order=payable_order).count() == 1


def test_a_chave_antiga_nao_passa_por_cima_do_uuid(payable_order, card_method, manager_user):  # noqa: F811
    """O PDV manda a `idempotency_key` junto. Conferida antes do UUID, ela
    devolvia o recebimento sem olhar horário nem valor — achado no par Docker."""
    pid, agora = uuid.uuid4(), timezone.now()

    def receber(momento, subtipo, valor="7.00"):
        return register_payment(
            order=payable_order, user=manager_user, payment_method_id=card_method.id,
            amount=valor, metadata={"card_subtype": subtipo}, payment_id=pid,
            client_updated_at=momento, idempotency_key=f"chave-{pid}",
        )

    receber(agora, "credit", valor="5.00")
    receber(agora + timedelta(seconds=10), "debit", valor="7.00")
    receber(agora + timedelta(seconds=5), "credit", valor="5.00")
    pagamento = Payment.all_objects.get(pk=pid)
    assert (pagamento.card_subtype, pagamento.amount) == ("debit", Decimal("7.00"))


def test_horario_sem_fuso_nao_vira_500(api_client, payable_order, card_method):  # noqa: F811
    """Achado na revisão: horário sem fuso comparado com o gravado (com fuso)
    estourava `TypeError` — 500, que o PDV reenvia para sempre. Sem fuso é UTC."""
    pid = str(uuid.uuid4())
    corpo = {"payment_method": str(card_method.id), "amount": "5.00", "id": pid,
             "client_updated_at": "2026-10-09T10:00:00Z", "metadata": {"card_subtype": "credit"}}
    url = f"/api/v1/orders/{payable_order.id}/pay/"

    assert api_client.post(url, corpo, format="json").status_code == 201
    mais_novo = api_client.post(url, {**corpo, "amount": "7.00",
                                      "client_updated_at": "2026-10-09T10:00:05"}, format="json")
    assert mais_novo.status_code == 201, mais_novo.content
    assert Decimal(mais_novo.json()["amount"]) == Decimal("7.00")
