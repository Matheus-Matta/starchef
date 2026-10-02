"""Desconto digitado no PDV: o caixa digita, um gerente APROVA, e fica registrado.

O gerente aprova pelo próprio cargo. O operador de caixa precisa de alguém que
libere ali mesmo — a senha de ações do caixa, ou o login de quem tem
`cash.approve`. O pedido guarda quem aprovou, como e quando; a auditoria guarda
de quanto para quanto.
"""
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserProfile
from apps.accounts.role_catalog import ensure_system_roles
from apps.core.models import AuditLog
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido(restaurant, branch, manager_user):
    restaurant.cash_action_password = make_password("senha-operacao")
    restaurant.save(update_fields=["cash_action_password"])
    novo = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    produto = Product.objects.create(
        account=restaurant.account, restaurant=restaurant, branch=branch, name="Prato",
        internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("50.00"),
    )
    add_order_item(order=novo, product=produto, quantity=2, user=manager_user)
    return novo


@pytest.fixture
def caixa(account, restaurant, branch):
    user = get_user_model().objects.create_user(username="operador", password="x", email="op@t.com")
    UserProfile.objects.create(
        account=account, user=user, role=ensure_system_roles(account)["cashier"],
        restaurant=restaurant, branch=branch,
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _fechar(cliente, pedido, **corpo):
    return cliente.post(f"/api/v1/orders/{pedido.pk}/close/", {"service_fee_enabled": False, **corpo},
                        format="json")


def test_gerente_aprova_pelo_proprio_cargo_e_fica_registrado(api_client, pedido, manager_user):
    resposta = _fechar(api_client, pedido, discount="15.00")

    assert resposta.status_code == 200, resposta.content
    pedido.refresh_from_db()
    assert pedido.discount == Decimal("15.00") and pedido.total == Decimal("85.00")
    assert (pedido.discount_authorization, pedido.discount_authorized_by_id) == ("own", manager_user.pk)
    assert pedido.discount_authorized_at is not None
    log = AuditLog.all_objects.filter(metadata__event="order_discount_approved").get()
    assert (log.metadata["from"], log.metadata["to"]) == ("0.00", "15.00")


def test_caixa_sem_aprovacao_recebe_403_e_nada_muda(caixa, pedido):
    resposta = _fechar(caixa, pedido, discount="15.00")

    assert resposta.status_code == 403
    pedido.refresh_from_db()
    assert pedido.discount == Decimal("0.00")
    assert pedido.status == Order.STATUS_OPEN
    assert not AuditLog.all_objects.filter(metadata__event="order_discount_approved").exists()


def test_senha_errada_tambem_e_403(caixa, pedido):
    assert _fechar(caixa, pedido, discount="15.00", cash_password="errada").status_code == 403
    pedido.refresh_from_db()
    assert pedido.discount == Decimal("0.00")


def test_caixa_com_senha_de_acoes_aprova_e_registra(caixa, pedido):
    resposta = _fechar(caixa, pedido, discount="15.00", cash_password="senha-operacao")

    assert resposta.status_code == 200, resposta.content
    pedido.refresh_from_db()
    assert pedido.discount == Decimal("15.00")
    # A senha é do restaurante, não de uma pessoa: registra COMO, sem "quem".
    assert pedido.discount_authorization == "cash_password"
    assert pedido.discount_authorized_by_id is None and pedido.discount_authorized_at


def test_gerente_libera_pelo_login(caixa, pedido, manager_user):
    manager_user.set_password("senha-do-gerente")
    manager_user.save()

    resposta = _fechar(caixa, pedido, discount="15.00", authorization_username=manager_user.username,
                       authorization_password="senha-do-gerente")

    assert resposta.status_code == 200, resposta.content
    pedido.refresh_from_db()
    assert (pedido.discount_authorization, pedido.discount_authorized_by_id) == ("delegated", manager_user.pk)


def test_fechar_de_novo_com_o_mesmo_desconto_nao_pede_outra_vez(api_client, caixa, pedido):
    _fechar(api_client, pedido, discount="15.00")
    Order.all_objects.filter(pk=pedido.pk).update(status=Order.STATUS_OPEN)

    assert _fechar(caixa, pedido, discount="15.00").status_code == 200
    assert _fechar(caixa, pedido, discount="20.00").status_code == 403


def test_tirar_o_desconto_nao_pede_aprovacao_e_limpa_o_registro(api_client, caixa, pedido):
    _fechar(api_client, pedido, discount="15.00")
    Order.all_objects.filter(pk=pedido.pk).update(status=Order.STATUS_OPEN)

    assert _fechar(caixa, pedido, discount="0").status_code == 200
    pedido.refresh_from_db()
    assert (pedido.discount, pedido.discount_authorization, pedido.discount_authorized_by_id) == (
        Decimal("0.00"), "", None,
    )


@pytest.mark.parametrize("valor", ["100.01", "-5", "abc"], ids=["acima-do-subtotal", "negativo", "texto"])
def test_desconto_invalido_e_400(api_client, pedido, valor):
    assert _fechar(api_client, pedido, discount=valor).status_code == 400
    pedido.refresh_from_db()
    assert pedido.discount == Decimal("0.00")


def test_desconto_e_cupom_juntos_nao_passam_do_subtotal(api_client, pedido):
    """Cada um cabia sozinho; a soma zerava o total e a NFC-e era recusada."""
    Order.all_objects.filter(pk=pedido.pk).update(coupon_discount=Decimal("90.00"))

    assert _fechar(api_client, pedido, discount="15.00").status_code == 400


def test_aprovacao_sobe_na_sincronizacao(api_client, pedido, manager_user):
    """Campo novo não tem trava automática: confere que entra no payload."""
    import apps.synchronization.catalog  # noqa: F401 — registra o catálogo
    from apps.synchronization.services import serialization
    from apps.synchronization.services.registry import registry

    _fechar(api_client, pedido, discount="15.00")
    pedido.refresh_from_db()

    campos = serialization.serialize(pedido, registry.get("order"))

    assert campos["discount_authorization"] == "own"
    assert str(campos["discount_authorized_by_id"]) == str(manager_user.pk)
    assert campos["discount_authorized_at"]
