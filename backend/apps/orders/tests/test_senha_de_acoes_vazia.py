"""Restaurante sem senha de ações NÃO tem senha — não tem uma padrão.

A autorização de cancelamento aceitava a string fixa `12345678` sempre que
`cash_action_password` estivesse vazia. E vazia é o estado NORMAL da loja: a
senha é excluída da sincronização, então toda instalação local nasce com o
campo em branco.

O resultado é uma credencial embutida valendo exatamente onde a de verdade não
chega — e a loja é o lado que fica sem supervisão quando a internet cai.

Movimento de caixa (`payments/services.py`) já fazia o certo: sem senha
gravada, recusa. Cancelamento fazia o oposto.
"""
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.hashers import make_password

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order


pytestmark = pytest.mark.django_db


def _pedido(restaurant, branch, user):
    """Pedido COM consumo lançado.

    Pedido vazio é descartável sem senha nenhuma (é comanda aberta que não
    virou venda), e um teste sobre autorização feito em cima de um desses
    passaria sem exercitar nada.
    """
    pedido = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user
    )
    produto = Product.objects.create(
        account=restaurant.account,
        restaurant=restaurant,
        branch=branch,
        name="Coxinha",
        internal_code=f"P{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("6.00"),
    )
    add_order_item(order=pedido, product=produto, quantity=1, user=user)
    pedido.refresh_from_db()
    return pedido


@pytest.fixture
def sem_carencia(restaurant):
    """A carência libera o cancelamento sem senha nenhuma, e esconderia tudo."""
    restaurant.cancellation_grace_seconds = 0
    restaurant.save(update_fields=["cancellation_grace_seconds", "updated_at"])
    return restaurant


def _tentar_cancelar(client, pedido, senha):
    return client.post(
        f"/api/v1/orders/{pedido.id}/cancel/",
        {"reason": "Cliente desistiu", "cash_password": senha},
        format="json",
    )


def test_senha_vazia_nao_aceita_a_string_fixa(
    api_client, sem_carencia, branch, manager_user
):
    """O defeito. `12345678` cancelava pedido em qualquer loja recém-instalada."""
    pedido = _pedido(sem_carencia, branch, manager_user)

    resposta = _tentar_cancelar(api_client, pedido, "12345678")

    pedido.refresh_from_db()
    assert pedido.status != Order.STATUS_CANCELLED, (
        "a string fixa `12345678` autorizou o cancelamento"
    )
    assert resposta.status_code in (400, 403), resposta.status_code


def test_senha_vazia_recusa_qualquer_senha(
    api_client, sem_carencia, branch, manager_user
):
    """Sem senha gravada não existe senha certa — o caminho é outro.

    Quem precisa cancelar continua tendo a autorização por LOGIN de gerente,
    que é nominal e fica na auditoria. É melhor do que uma senha que todo
    mundo sabe.
    """
    pedido = _pedido(sem_carencia, branch, manager_user)

    _tentar_cancelar(api_client, pedido, "qualquer-coisa")

    pedido.refresh_from_db()
    assert pedido.status != Order.STATUS_CANCELLED


def test_com_senha_gravada_a_senha_certa_continua_valendo(
    api_client, sem_carencia, branch, manager_user
):
    """A regra que não pode cair junto com o conserto."""
    sem_carencia.cash_action_password = make_password("senha-da-casa")
    sem_carencia.save(update_fields=["cash_action_password", "updated_at"])
    pedido = _pedido(sem_carencia, branch, manager_user)

    resposta = _tentar_cancelar(api_client, pedido, "senha-da-casa")

    assert resposta.status_code == 200, resposta.data
    pedido.refresh_from_db()
    assert pedido.status == Order.STATUS_CANCELLED


def test_com_senha_gravada_a_string_fixa_nao_vale(
    api_client, sem_carencia, branch, manager_user
):
    sem_carencia.cash_action_password = make_password("senha-da-casa")
    sem_carencia.save(update_fields=["cash_action_password", "updated_at"])
    pedido = _pedido(sem_carencia, branch, manager_user)

    _tentar_cancelar(api_client, pedido, "12345678")

    pedido.refresh_from_db()
    assert pedido.status != Order.STATUS_CANCELLED
