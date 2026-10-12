"""As formas de pagamento podem vir da mais usada para a menos usada.

O PDV abria o pagamento com a forma da ordem de cadastro, e o caixa trocava
para Pix ou débito em quase toda venda — um gesto a mais por cliente. Com
`?ordering=-uso,name` a lista vem pela contagem de recebimentos aprovados dos
últimos 90 dias, e a primeira (a que o PDV seleciona) é a do dia a dia.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services import create_order
from apps.payments.models import Payment, PaymentMethod

pytestmark = pytest.mark.django_db


@pytest.fixture
def formas(account, restaurant, branch, manager_user):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)

    def forma(nome, tipo, recebimentos, *, status=Payment.STATUS_APPROVED, dias=0):
        criada = PaymentMethod.objects.create(account=account, restaurant=restaurant,
                                              branch=branch, name=nome, method_type=tipo)
        for _ in range(recebimentos):
            pagamento = Payment.objects.create(
                account=account, restaurant=restaurant, branch=branch, order=pedido,
                payment_method=criada, amount=Decimal("10.00"), status=status)
            if dias:
                Payment.all_objects.filter(pk=pagamento.pk).update(
                    paid_at=timezone.now() - timedelta(days=dias))
        return criada

    forma("Espécie", PaymentMethod.TYPE_CASH, 1)
    forma("Pix", PaymentMethod.TYPE_PIX, 3)
    forma("Cartão", PaymentMethod.TYPE_CARD, 2)
    # Muito usada, mas há mais de 90 dias: o hábito de hoje é outro.
    forma("Cheque", PaymentMethod.TYPE_CASH, 5, dias=120)
    # Estornados não contam: não foram uso de verdade.
    forma("Vale", PaymentMethod.TYPE_VOUCHER, 4, status=Payment.STATUS_REFUNDED)


NOSSAS = {"Espécie", "Pix", "Cartão", "Cheque", "Vale"}


def _nomes(resposta):
    """Só as formas deste teste: o restaurante nasce com as suas padrão."""
    corpo = resposta.json()
    return [f["name"] for f in corpo.get("results", corpo) if f["name"] in NOSSAS]


def test_mais_usada_primeiro_e_empate_pelo_nome(api_client, formas):
    resposta = api_client.get("/api/v1/payments/methods/", {"ordering": "-uso,name"})

    assert resposta.status_code == 200, resposta.content
    assert _nomes(resposta) == ["Pix", "Cartão", "Espécie", "Cheque", "Vale"]


def test_sem_pedir_a_ordem_por_uso_a_lista_nao_muda(api_client, formas):
    """O painel continua listando como sempre: a ordem por uso é pedida."""
    resposta = api_client.get("/api/v1/payments/methods/", {"ordering": "name"})

    assert _nomes(resposta) == sorted(_nomes(resposta))
