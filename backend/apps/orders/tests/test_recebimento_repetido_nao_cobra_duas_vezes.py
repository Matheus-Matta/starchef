"""O recebimento repetido pelo operador não vira um segundo pagamento.

O PDV gera a chave do recebimento quando ele entra na tela e a manda no CORPO
(`idempotency_key`) em toda tentativa. Mas cada chamada HTTP leva também um
`Idempotency-Key` NOVO no cabeçalho, e a rota de pagamento preferia o do
cabeçalho: a repetição depois de uma falha de rede chegava com chave nova e
virava outro pagamento. A chave do corpo — feita exatamente para isso — nunca
era usada. Achado pela simulação do dia a dia (`loadtest/dia_a_dia`).
"""
import uuid

import pytest

from apps.orders.tests.conftest import criar_com_item
from apps.payments.models import Payment, PaymentMethod

pytestmark = pytest.mark.django_db


def test_mesma_chave_no_corpo_com_cabecalhos_diferentes_paga_uma_vez(
    api_client, restaurant, branch, account, produto, sem_caixa_obrigatorio
):
    pix = PaymentMethod.objects.create(account=account, restaurant=restaurant, branch=branch,
                                       name="PIX", method_type=PaymentMethod.TYPE_PIX)
    pedido = criar_com_item(api_client, restaurant=restaurant, produto=produto, tipo="counter",
                            quantidade=2).json()
    metade = f"{float(pedido['total']) / 2:.2f}"
    corpo = {"payment_method": str(pix.pk), "amount": metade, "idempotency_key": "caixa-1-rec-7"}

    for _ in range(2):
        resposta = api_client.post(f"/api/v1/orders/{pedido['id']}/pay/", corpo, format="json",
                                   HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert resposta.status_code in (200, 201), resposta.content

    assert Payment._base_manager.filter(order_id=pedido["id"]).count() == 1
