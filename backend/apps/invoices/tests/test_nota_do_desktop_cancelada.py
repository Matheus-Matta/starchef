# ruff: noqa: F811 (a fixture importada também é o argumento dos testes)
"""Cancelamento de NFC-e do StarChef Desktop: o evento chega já homologado."""
import pytest

from apps.invoices.models import Invoice
from apps.invoices.tests.test_nota_do_desktop import URL, enviar, montar, pedido  # noqa: F401
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


def test_cancelamento_homologado_no_terminal_libera_o_pedido(api_client, pedido):
    chave, xml = montar()
    evento = {"chave": chave, "protocolo": "135260000000099", "justificativa": "cliente desistiu da compra"}

    def cancelar(**troca):
        return api_client.post(URL, {"order": str(pedido.pk), "cancelamento": {**evento, **troca}}, format="json")

    assert cancelar().status_code == 409  # nota ainda não registrada
    enviar(api_client, pedido, xml)
    with pytest.raises(Exception, match="Desktop"):
        _cancelar_pedido(pedido)
    for troca in ({"protocolo": ""}, {"protocolo": "abc"}, {"justificativa": "curta"}):
        assert cancelar(**troca).status_code == 400
    assert cancelar(chave="3" * 44).status_code == 409
    assert cancelar(verificar=True, protocolo="").status_code == 200
    assert Invoice.all_objects.get(order=pedido).status == Invoice.STATUS_ISSUED  # só conferiu
    assert cancelar().status_code == 200
    assert cancelar().status_code == 200  # reenvio
    assert Invoice.all_objects.get(order=pedido).status == Invoice.STATUS_CANCELLED
    _cancelar_pedido(pedido)
    pedido.refresh_from_db()
    assert pedido.status == Order.STATUS_CANCELLED
    assert enviar(api_client, pedido, xml).status_code == 409  # não volta a ser autorizada


def test_contingencia_pendente_nao_aceita_cancelamento(api_client, pedido):
    chave, xml = montar(tp_emis="9", protocolo=False)
    enviar(api_client, pedido, xml)
    r = api_client.post(URL, {"order": str(pedido.pk), "cancelamento": {
        "chave": chave, "protocolo": "135260000000099", "justificativa": "cliente desistiu da compra"}}, format="json")
    assert r.status_code == 409


def _cancelar_pedido(pedido):
    from apps.orders.services import cancel_order

    cancel_order(pedido, pedido.created_by, "cliente desistiu da compra")
