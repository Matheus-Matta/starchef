"""O comprovante do pedido CANCELADO, ligado e desligado no restaurante.

Antes não existia: o cancelamento só gerava o aviso para a COZINHA. Quem
precisava provar ao cliente (ou ao caixa) que a venda foi desfeita não tinha
papel nenhum para mostrar.
"""
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.hashers import make_password

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.printers.models import Printer, PrintJob

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def senha_do_caixa(restaurant):
    restaurant.cash_action_password = make_password("4321")
    restaurant.save(update_fields=["cash_action_password"])


@pytest.fixture
def impressora(account, restaurant, branch, admin_user):
    return Printer.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Caixa",
        created_by=admin_user, updated_by=admin_user,
    )


@pytest.fixture
def pedido_com_item(account, restaurant, branch, admin_user):
    pedido = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=admin_user,
    )
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Coca-Cola KS",
        internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("5.99"),
    )
    add_order_item(order=pedido, product=produto, quantity=2, user=admin_user)
    return pedido


def _cancelar(cliente, pedido, motivo="Cliente desistiu"):
    return cliente.post(
        f"/api/v1/orders/{pedido.id}/cancel/",
        {"reason": motivo, "cash_password": "4321"},
        format="json",
    )


def test_restaurante_ligado_cancelar_gera_o_comprovante(
    restaurant, impressora, pedido_com_item, admin_client
):
    restaurant.print_cancellation_receipt = True
    restaurant.save(update_fields=["print_cancellation_receipt"])

    resposta = _cancelar(admin_client, pedido_com_item)

    assert resposta.status_code == 200, resposta.data
    impressao = resposta.data["cancellation_print"]
    texto = impressao["payload"]["text_content"]
    assert "COMPROVANTE DE CANCELAMENTO" in texto
    assert "Coca-Cola KS" in texto
    assert "11.98" in texto
    assert "Cliente desistiu" in texto
    job = PrintJob._base_manager.get(pk=impressao["print_job_id"])
    assert job.job_type == PrintJob.TYPE_ORDER_CANCEL


def test_padrao_desligado_nao_gera_papel(pedido_com_item, admin_client):
    resposta = _cancelar(admin_client, pedido_com_item)

    assert resposta.status_code == 200, resposta.data
    assert resposta.data.get("cancellation_print") is None
    assert not PrintJob._base_manager.filter(job_type=PrintJob.TYPE_ORDER_CANCEL).exists()


def test_pedido_vazio_descartado_nunca_imprime(restaurant, branch, admin_user, admin_client):
    """Não há venda a comprovar: imprimir seria papel para nada."""
    restaurant.print_cancellation_receipt = True
    restaurant.save(update_fields=["print_cancellation_receipt"])
    vazio = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=admin_user,
    )

    resposta = admin_client.post(f"/api/v1/orders/{vazio.id}/cancel/", {}, format="json")

    assert resposta.status_code == 200, resposta.data
    assert resposta.data.get("cancellation_print") is None


def test_reimprimir_pelo_endpoint_de_impressao_mesmo_desligado(
    impressora, pedido_com_item, admin_client
):
    """O cliente pede o comprovante depois: a opção do restaurante não impede."""
    _cancelar(admin_client, pedido_com_item)

    resposta = admin_client.post(
        f"/api/v1/orders/{pedido_com_item.id}/print/",
        {"job_type": PrintJob.TYPE_ORDER_CANCEL},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    assert "COMPROVANTE DE CANCELAMENTO" in resposta.data["payload"]["text_content"]


def test_sem_impressora_o_cancelamento_vale_e_responde_200(restaurant, pedido_com_item, admin_client):
    """Imprimir não derruba o cancelamento. Antes da trava, a falta de
    impressora devolvia 400 DEPOIS de cancelar: o PDV lia "falhou" e o pedido
    já estava cancelado."""
    restaurant.print_cancellation_receipt = True
    restaurant.save(update_fields=["print_cancellation_receipt"])

    resposta = _cancelar(admin_client, pedido_com_item)

    assert resposta.status_code == 200, resposta.data
    assert resposta.data["status"] == Order.STATUS_CANCELLED
    assert resposta.data.get("cancellation_print") is None
    assert "impressora" in resposta.data["cancellation_print_error"].lower()
