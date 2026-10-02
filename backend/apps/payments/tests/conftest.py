"""Sessões, formas e pagamentos para os testes da divergência de vendas."""
import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import UserProfile
from apps.accounts.role_catalog import ensure_system_roles
from apps.orders.models import Order
from apps.payments.models import CashRegister, Payment, PaymentMethod

URL = "/api/v1/cash-discrepancies/"
RELATORIO = "/api/v1/cash-discrepancy-report/"


@pytest.fixture
def sessao_de_caixa(account, restaurant, branch, admin_user):
    def criar(**extra):
        return CashRegister.objects.create(
            account=account, restaurant=restaurant, branch=branch, opened_by=admin_user,
            opening_amount="100.00", expected_amount="100.00",
            created_by=admin_user, updated_by=admin_user, **extra,
        )

    return criar


@pytest.fixture
def forma(account, restaurant, branch, admin_user):
    def criar(nome, tipo=PaymentMethod.TYPE_PIX):
        return PaymentMethod.objects.create(
            account=account, restaurant=restaurant, branch=branch, name=nome, method_type=tipo,
            created_by=admin_user, updated_by=admin_user,
        )

    return criar


@pytest.fixture
def venda(account, restaurant, branch, admin_user):
    """Um pagamento aprovado vinculado à sessão (como o PDV grava)."""
    contador = iter(range(5000, 9000))

    def criar(sessao, metodo, valor):
        pedido = Order.objects.create(
            account=account, restaurant=restaurant, branch=branch, sequence=next(contador),
            order_type=Order.TYPE_COUNTER, responsible_user=admin_user,
            created_by=admin_user, updated_by=admin_user,
        )
        return Payment.objects.create(
            account=account, restaurant=restaurant, branch=branch, order=pedido,
            payment_method=metodo, amount=valor, metadata={"cash_register": str(sessao.pk)},
            created_by=admin_user, updated_by=admin_user,
        )

    return criar


@pytest.fixture
def caixa_client(account, restaurant, branch):
    """Operador de caixa: vê o próprio caixa, mas não registra nem regulariza."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    user = get_user_model().objects.create_user(username="operador", password="x", email="op@test.com")
    UserProfile.objects.create(
        account=account, user=user, role=ensure_system_roles(account)["cashier"],
        restaurant=restaurant, branch=branch,
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def corpo(sessao, *formas):
    """`formas`: pares (metodo, "valor")."""
    return {
        "cash_register": str(sessao.pk),
        "reason": "Vendas realizadas sem registro no PDV (movimento alto).",
        "by_payment_method": [{"payment_method": str(m.pk), "amount": v} for m, v in formas],
    }
