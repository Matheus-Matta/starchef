"""Conferência do fechamento: o que o caixa espera, e quanto de diferença tolera.

Duas partes:

1. A SOMA (regressão, congelada antes de mexer na regra): abertura + venda em
   dinheiro LÍQUIDA de troco + suprimento aprovado − sangria aprovada. Sangria
   pendente não sai da gaveta até ser aprovada, então não entra.
2. A TOLERÂNCIA (`Restaurant.cash_closing_tolerance`, padrão R$ 0,50): uma
   diferença de centavos — moeda que caiu, troco arredondado — fechava o caixa
   como "pendente de aprovação" e exigia gerente para R$ 0,10. Até a margem,
   em falta OU em sobra, o caixa fecha. Os valores reais ficam gravados como
   estão: a margem não cria ajuste nem esconde a diferença.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import CashMovement, CashRegister, PaymentMethod
from apps.payments.services import (
    approve_cash_operation,
    close_cash_register,
    create_cash_movement,
    open_cash_register,
    register_payment,
)

pytestmark = pytest.mark.django_db

ESPERADO = Decimal("153.00")  # 100 + 43 + 20 − 10


@pytest.fixture
def caixa(account, restaurant, branch, admin_user):
    """Um dia de caixa com cada tipo de movimento, pelos serviços reais."""
    with tenant_context(account):
        sessao = open_cash_register(
            restaurant=restaurant, branch=branch, user=admin_user, opening_amount=Decimal("100.00")
        )
        produto = Product.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="Prato",
            internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("21.50"),
        )
        dinheiro = PaymentMethod.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="Dinheiro",
            method_type=PaymentMethod.TYPE_CASH,
        )
        pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=admin_user)
        add_order_item(order=pedido, product=produto, quantity=2, user=admin_user)
        pedido.refresh_from_db()
        # R$ 50 numa conta de R$ 43: R$ 7 de troco saem da gaveta.
        register_payment(
            order=pedido, user=admin_user, payment_method_id=dinheiro.pk,
            amount=Decimal("50.00"), cash_register_id=sessao.pk,
        )
        for tipo, valor, aprovar in (
            (CashMovement.TYPE_SUPPLY, "20.00", True),
            (CashMovement.TYPE_WITHDRAWAL, "10.00", True),
            (CashMovement.TYPE_WITHDRAWAL, "30.00", False),  # pendente: não saiu
        ):
            movimento = create_cash_movement(
                cash_register=sessao, user=admin_user, movement_type=tipo, amount=valor, reason="teste",
            )
            if aprovar:
                approve_cash_operation(cash_register=sessao, user=admin_user, reason="ok", movement=movimento)
    return sessao


def _fechar(sessao, usuario, contado):
    with tenant_context(sessao.account):
        return close_cash_register(cash_register=sessao, user=usuario, actual_amount=contado)


def test_esperado_e_abertura_venda_liquida_suprimento_e_sangria_aprovados(caixa, admin_user):
    fechado = _fechar(caixa, admin_user, ESPERADO)

    assert fechado.expected_amount == ESPERADO
    assert fechado.difference_amount == Decimal("0.00")
    assert fechado.status == CashRegister.STATUS_CLOSED


@pytest.mark.parametrize("diferenca", ["-0.50", "-0.49", "0.49", "0.50"])
def test_diferenca_dentro_da_margem_fecha_sem_aprovacao(caixa, admin_user, diferenca):
    fechado = _fechar(caixa, admin_user, ESPERADO + Decimal(diferenca))

    assert fechado.status == CashRegister.STATUS_CLOSED
    assert fechado.closed_at is not None
    # O que foi contado e a diferença ficam como são: nada de ajuste fictício.
    assert fechado.actual_amount == ESPERADO + Decimal(diferenca)
    assert fechado.difference_amount == Decimal(diferenca)


@pytest.mark.parametrize("diferenca", ["-0.51", "0.51", "-5.00"])
def test_diferenca_acima_da_margem_vai_para_aprovacao(caixa, admin_user, diferenca):
    fechado = _fechar(caixa, admin_user, ESPERADO + Decimal(diferenca))

    assert fechado.status == CashRegister.STATUS_PENDING_APPROVAL
    assert fechado.pending_operation == "closing"
    assert fechado.difference_amount == Decimal(diferenca)


def test_margem_zero_volta_a_exigir_aprovacao_para_qualquer_centavo(caixa, admin_user, restaurant):
    restaurant.cash_closing_tolerance = Decimal("0.00")
    restaurant.save(update_fields=["cash_closing_tolerance"])

    fechado = _fechar(caixa, admin_user, ESPERADO + Decimal("0.01"))

    assert fechado.status == CashRegister.STATUS_PENDING_APPROVAL


def test_margem_nasce_em_cinquenta_centavos_e_nao_aceita_negativa(restaurant):
    from django.core.exceptions import ValidationError

    assert restaurant.cash_closing_tolerance == Decimal("0.50")
    restaurant.cash_closing_tolerance = Decimal("-0.01")
    with pytest.raises(ValidationError):
        restaurant.full_clean()


def test_margem_viaja_na_sincronizacao_e_e_espelhada_na_filial(restaurant):
    """Campo novo não tem trava automática na sincronização: este teste é a trava."""
    from apps.restaurants.models import Branch
    import apps.synchronization.catalog  # noqa: F401 — registra as entradas
    from apps.synchronization.services.registry import registry
    from apps.synchronization.services.serialization import serialize

    restaurant.cash_closing_tolerance = Decimal("1.25")
    restaurant.save()

    entrada = registry.get("restaurant")
    assert serialize(restaurant, entrada)["cash_closing_tolerance"] == "1.25"
    # A filial espelhada é a que `sync_branch_for_restaurant` mantém (a primeira).
    espelho = Branch.all_objects.filter(restaurant=restaurant).order_by("created_at").first()
    assert espelho.cash_closing_tolerance == Decimal("1.25")
