"""A fila offline do PDV reenvia operações; o servidor não pode duplicá-las."""

from decimal import Decimal

import pytest

from rest_framework_simplejwt.tokens import AccessToken

from apps.core.models import IdempotencyRecord
from apps.orders.models import Order, OrderItem


@pytest.fixture
def authenticated(api_client, manager_user):
    """O middleware de tenant autentica pelo JWT, antes do DRF.

    Por isso `force_authenticate` não serve aqui: é preciso um token real no
    header, como o PDV envia.
    """
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )
    return api_client


def _create_order(client, restaurant, key=None):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return client.post(
        "/api/v1/orders/",
        {"restaurant": str(restaurant.id), "order_type": Order.TYPE_COUNTER},
        format="json",
        **headers,
    )


@pytest.mark.django_db
def test_reenvio_com_a_mesma_chave_nao_cria_segundo_pedido(authenticated, restaurant):
    first = _create_order(authenticated, restaurant, key="pdv-abc123456789")
    assert first.status_code == 201, first.content

    second = _create_order(authenticated, restaurant, key="pdv-abc123456789")

    assert second.status_code == 201
    # A resposta é a original, byte a byte: o cliente não percebe diferença.
    assert second.json()["id"] == first.json()["id"]
    assert second["Idempotent-Replay"] == "true"
    assert Order.all_objects.count() == 1


@pytest.mark.django_db
def test_sem_chave_cada_envio_cria_um_pedido(authenticated, restaurant):
    _create_order(authenticated, restaurant)
    _create_order(authenticated, restaurant)

    # Sem a chave não há como saber que é a mesma intenção.
    assert Order.all_objects.count() == 2


@pytest.mark.django_db
def test_chaves_diferentes_criam_pedidos_diferentes(authenticated, restaurant):
    _create_order(authenticated, restaurant, key="pdv-primeira-chave")
    _create_order(authenticated, restaurant, key="pdv-segunda-chave")

    assert Order.all_objects.count() == 2


@pytest.mark.django_db
def test_mesma_chave_para_outra_operacao_e_recusada(authenticated, restaurant, table):
    _create_order(authenticated, restaurant, key="pdv-chave-reaproveitada")

    conflicting = authenticated.post(
        "/api/v1/orders/",
        {"restaurant": str(restaurant.id), "order_type": Order.TYPE_TABLE, "table": str(table.id)},
        format="json",
        HTTP_IDEMPOTENCY_KEY="pdv-chave-reaproveitada",
    )

    # Devolver a resposta antiga aqui esconderia um erro do cliente.
    assert conflicting.status_code == 409
    assert "idempot" in conflicting.json()["detail"].lower()


@pytest.mark.django_db
def test_falha_nao_e_memorizada_e_pode_ser_repetida(authenticated):
    invalid = authenticated.post(
        "/api/v1/orders/",
        {"order_type": "inexistente"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="pdv-chave-de-erro",
    )
    assert invalid.status_code >= 400

    # Guardar o erro impediria o operador de tentar de novo após corrigir.
    assert not IdempotencyRecord.objects.filter(key="pdv-chave-de-erro").exists()


@pytest.mark.django_db
def test_item_adicionado_duas_vezes_com_a_mesma_chave_entra_uma_vez(
    authenticated,
    restaurant,
    product,
):
    order = _create_order(authenticated, restaurant, key="pdv-pedido-item").json()
    payload = {"product": str(product.id), "quantity": "2"}

    first = authenticated.post(
        f"/api/v1/orders/{order['id']}/items/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="pdv-item-unico",
    )
    second = authenticated.post(
        f"/api/v1/orders/{order['id']}/items/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="pdv-item-unico",
    )

    assert first.status_code in (200, 201), first.content
    assert second.status_code == first.status_code
    # O cliente pediu o produto uma vez; o reenvio não pode cobrar de novo.
    assert OrderItem.all_objects.filter(order_id=order["id"]).count() == 1


@pytest.mark.django_db
def test_o_registro_fica_isolado_por_conta(authenticated, restaurant, account):
    _create_order(authenticated, restaurant, key="pdv-chave-compartilhada")

    record = IdempotencyRecord.objects.get(key="pdv-chave-compartilhada")

    # Contas diferentes podem usar a mesma chave sem interferência.
    assert record.account_id == account.id
    assert record.status_code == 201
    assert record.response_body["id"]


@pytest.mark.django_db
def test_login_nao_passa_pela_deduplicacao(api_client, manager_user):
    """Repetir o login precisa continuar funcionando."""
    for _ in range(2):
        response = api_client.post(
            "/api/v1/auth/login/",
            {"username": "manager", "password": "secret123"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pdv-login",
        )
        assert response.status_code == 200

    assert not IdempotencyRecord.objects.filter(key="pdv-login").exists()


@pytest.mark.django_db
def test_pagamento_reenviado_nao_cobra_duas_vezes(
    authenticated,
    restaurant,
    branch,
    product,
    payment_method,
    manager_user,
):
    from apps.payments.services import open_cash_register

    open_cash_register(restaurant=restaurant, branch=branch, user=manager_user)
    order = _create_order(authenticated, restaurant, key="pdv-pedido-pgto").json()
    authenticated.post(
        f"/api/v1/orders/{order['id']}/items/",
        {"product": str(product.id), "quantity": "1"},
        format="json",
    )
    authenticated.post(f"/api/v1/orders/{order['id']}/close/", {}, format="json")

    payload = {
        "payment_method": str(payment_method.id),
        "amount": str(Decimal("25.00")),
    }
    first = authenticated.post(
        f"/api/v1/orders/{order['id']}/pay/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="pdv-pagamento-unico",
    )
    second = authenticated.post(
        f"/api/v1/orders/{order['id']}/pay/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="pdv-pagamento-unico",
    )

    assert first.status_code in (200, 201), first.content
    assert second.status_code == first.status_code
    assert second["Idempotent-Replay"] == "true"

    from apps.payments.models import Payment

    assert Payment.all_objects.filter(order_id=order["id"]).count() == 1
