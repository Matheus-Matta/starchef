"""A NFC-e sai em segundo plano: o "Concluir" do caixa não espera a SEFAZ.

A emissão rodava no `on_commit` do pagamento, DENTRO da requisição que
concluiu a venda. O caixa esperava a SEFAZ inteira (de 1 s a 40 s, com o ACBr)
para a tela liberar, e passando de 20 s o PDV desistia, repetia e saía da tela
— e o DANFE já não saía (ver o teste da corrida, no fim).
"""
from decimal import Decimal
from unittest import mock

import pytest
from kombu.exceptions import OperationalError

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.tests.test_auto_issue_on_payment import _AutoIssueProvider, _pay
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import PaymentMethod

pytestmark = pytest.mark.django_db

ENFILEIRAR = "apps.invoices.tasks.emitir_nota_do_pedido_pago_task.delay"


@pytest.fixture
def cadastro_fiscal(account, restaurant, branch):
    # O assunto é a nota, não a gaveta.
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=_AutoIssueProvider.name, cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
    )


@pytest.fixture
def pedido(account, restaurant, branch, manager_user):
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code="P-SEGUNDO-PLANO", sale_price=Decimal("25.00"),
    )
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    pedido.refresh_from_db()
    return pedido


@pytest.fixture
def dinheiro_do_caixa(account, restaurant, branch, manager_user):
    return PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Dinheiro",
        method_type=PaymentMethod.TYPE_CASH, created_by=manager_user, updated_by=manager_user,
    )


def test_pagamento_integral_enfileira_a_nota_em_vez_de_esperar_a_sefaz(
    pedido, dinheiro_do_caixa, cadastro_fiscal, manager_user, django_capture_on_commit_callbacks
):
    """O defeito: o recebimento só respondia depois de a SEFAZ autorizar."""
    with mock.patch(ENFILEIRAR) as enfileirar, mock.patch(
        "apps.invoices.services.issue_invoice_for_paid_order"
    ) as emitir_agora:
        with django_capture_on_commit_callbacks(execute=True):
            _pay(pedido, dinheiro_do_caixa, manager_user)

    emitir_agora.assert_not_called()
    enfileirar.assert_called_once()
    assert enfileirar.call_args.args[0] == str(pedido.pk)


def test_sem_a_fila_do_celery_a_nota_e_emitida_na_hora(
    pedido, dinheiro_do_caixa, cadastro_fiscal, manager_user, django_capture_on_commit_callbacks
):
    """Redis fora não pode deixar venda paga sem nota: emite como antes."""
    with mock.patch(ENFILEIRAR, side_effect=OperationalError("redis fora")):
        with django_capture_on_commit_callbacks(execute=True):
            _pay(pedido, dinheiro_do_caixa, manager_user)

    assert Invoice.all_objects.filter(order=pedido, status=Invoice.STATUS_ISSUED).exists()


def test_a_tarefa_emite_a_nota_do_pedido_pago(
    pedido, dinheiro_do_caixa, cadastro_fiscal, manager_user, django_capture_on_commit_callbacks
):
    from apps.invoices.tasks import emitir_nota_do_pedido_pago_task

    with mock.patch(ENFILEIRAR):
        with django_capture_on_commit_callbacks(execute=True):
            _pay(pedido, dinheiro_do_caixa, manager_user)
    assert not Invoice.all_objects.filter(order=pedido).exists()

    emitir_nota_do_pedido_pago_task(str(pedido.pk), str(manager_user.pk), False)

    assert Invoice.all_objects.filter(order=pedido, status=Invoice.STATUS_ISSUED).exists()


def test_pdv_que_pede_a_nota_enquanto_ela_era_emitida_recebe_a_nota_e_nao_erro(
    api_client, account, restaurant, branch, pedido, cadastro_fiscal
):
    """Achado na loja: "Pedido ja possui nota fiscal emitida" e o DANFE não saía.

    O `/invoices/emit/` conferia "já tem nota?" ANTES de travar o pedido. Com a
    emissão automática ainda na SEFAZ, a resposta era "não"; ele esperava a
    trava, a outra emissão gravava a nota, e ele recusava com 400. O PDV
    desistia de imprimir, e o servidor também não imprimia (a nota é do
    terminal). Aqui a emissão automática termina no meio da espera.
    """
    from apps.invoices import services

    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    real = services.emit_fiscal_invoice

    def a_automatica_termina_durante_a_espera(pedido, **kwargs):
        real(pedido)
        return real(pedido, **kwargs)

    with mock.patch("apps.invoices.views.emit_fiscal_invoice", a_automatica_termina_durante_a_espera):
        resposta = api_client.post(
            "/api/v1/invoices/emit/", {"order": str(pedido.id)}, format="json"
        )

    assert resposta.status_code == 200, resposta.content
    nota = Invoice.all_objects.get(order=pedido)
    assert resposta.data["id"] == str(nota.id)
    assert resposta.data["printable"] is True

