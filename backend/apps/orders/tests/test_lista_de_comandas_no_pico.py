"""A lista de comandas no pico: uma consulta por TELA, não por cartão.

O `CommandViewSet` declarava a anotação que conta o pendente de todos os
cartões de uma vez — mas o mixin de tenant remonta o queryset e a jogava fora.
Cada cartão custava quatro consultas: 100 comandas, 405 consultas e um segundo
por página. Com 500 comandas abertas o PDV relia seis páginas a cada comanda
alterada, em cada terminal, e o servidor afogou.

O caminho rápido tem de responder EXATAMENTE o que o lento responde: estado,
quantidade e valor pendentes. É isso que o segundo teste trava.
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem, Order
from apps.orders.services import create_order
from apps.restaurants.models import Command
from apps.restaurants.serializers import CommandSerializer

pytestmark = pytest.mark.django_db

CAMPOS = ("status", "pending_items", "pending_total")


def _comanda(restaurant, branch, numero):
    return Command.objects.create(
        account=restaurant.account, restaurant=restaurant, branch=branch,
        number=numero, code=f"PICO-{numero:04d}",
    )


def _lista(cliente):
    resposta = cliente.get("/api/v1/commands/?page_size=100&is_active=true")
    assert resposta.status_code == 200, resposta.content
    return {linha["id"]: linha for linha in resposta.data["results"]}


def test_listar_comandas_custa_o_mesmo_com_2_ou_com_8(api_client, restaurant, branch, manager_user, produto):
    def cria(de, ate):
        for numero in range(de, ate):
            launch_item(command=_comanda(restaurant, branch, numero), product=produto, user=manager_user, quantity=1)

    cria(1, 3)
    with CaptureQueriesContext(connection) as com_dois:
        _lista(api_client)
    cria(3, 9)
    with CaptureQueriesContext(connection) as com_oito:
        _lista(api_client)

    assert len(com_oito) == len(com_dois), f"{len(com_dois)} consultas com 2, {len(com_oito)} com 8"


def test_lista_rapida_responde_igual_ao_caminho_lento(api_client, restaurant, branch, manager_user, produto):
    """Cada cartão num dos casos que separam "em uso" de "livre"."""
    com_item = _comanda(restaurant, branch, 1)
    launch_item(command=com_item, product=produto, user=manager_user, quantity=2)

    so_cancelado = _comanda(restaurant, branch, 2)
    launch_item(command=so_cancelado, product=produto, user=manager_user, quantity=1)

    item_apagado = _comanda(restaurant, branch, 3)
    launch_item(command=item_apagado, product=produto, user=manager_user, quantity=1)

    # O fluxo antigo: a comanda abre o pedido e o consumo mora nele.
    pedido_aberto = _comanda(restaurant, branch, 4)
    pedido_pago = _comanda(restaurant, branch, 5)
    vazia = _comanda(restaurant, branch, 6)
    with tenant_context(restaurant.account):
        CommandItem.objects.filter(command=so_cancelado).update(status=CommandItem.STATUS_CANCELLED)
        CommandItem.objects.filter(command=item_apagado).update(deleted_at=timezone.now())
        aberto = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
        pago = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
        Order.objects.filter(pk=pago.pk).update(status=Order.STATUS_PAID)
        Command.objects.filter(pk=pedido_aberto.pk).update(current_order_id=aberto.pk)
        Command.objects.filter(pk=pedido_pago.pk).update(current_order_id=pago.pk)

        # O caminho lento: cada cartão lido sozinho, sem anotação nenhuma.
        lento = {}
        for comanda in (com_item, so_cancelado, item_apagado, pedido_aberto, pedido_pago, vazia):
            dados = CommandSerializer(Command.objects.get(pk=comanda.pk)).data
            lento[str(comanda.pk)] = {campo: dados[campo] for campo in CAMPOS}

    rapido = {pk: {campo: linha[campo] for campo in CAMPOS} for pk, linha in _lista(api_client).items()}

    assert rapido == lento
    # E o lento é o que se espera de cada caso, para o teste não comparar
    # dois erros iguais.
    assert lento[str(com_item.pk)] == {"status": "occupied", "pending_items": 1, "pending_total": "50.00"}
    assert lento[str(so_cancelado.pk)]["status"] == "free"
    assert lento[str(item_apagado.pk)]["status"] == "free"
    assert lento[str(pedido_aberto.pk)]["status"] == "occupied"
    assert lento[str(pedido_pago.pk)]["status"] == "free"
    assert lento[str(vazia.pk)]["status"] == "free"


def test_lista_continua_na_ordem_do_numero(api_client, restaurant, branch, manager_user, produto):
    """A contagem da anotação vira GROUP BY, e o Django ignora `Meta.ordering`
    em consulta agrupada: a grade do PDV saía embaralhada (a paginação caía no
    desempate por id aleatório)."""
    for numero in (7, 2, 9, 1, 5):
        launch_item(command=_comanda(restaurant, branch, numero), product=produto, user=manager_user, quantity=1)

    resposta = api_client.get("/api/v1/commands/?page_size=100&is_active=true")

    assert [linha["number"] for linha in resposta.data["results"]] == [1, 2, 5, 7, 9]
