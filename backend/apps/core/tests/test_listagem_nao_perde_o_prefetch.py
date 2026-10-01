"""A listagem não pode fazer uma consulta por linha.

O mixin de tenant troca o queryset da view por `model.all_objects.all()` (para
enxergar a lixeira quando pedido) — e com isso jogava fora o `select_related`
e o `prefetch_related` declarados em TODA view. Cada pedido listado custava uma
dúzia de consultas: 10 pedidos, 125 consultas; 50 pedidos, um segundo inteiro.
Sob o movimento da loja o servidor enfileirava, o pool de conexões esgotava e
o caixa esperava quase um minuto para concluir a venda.
"""
import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import PaymentMethod
from apps.payments.services import register_payment

pytestmark = pytest.mark.django_db


def _vendedor(restaurant, branch, account, usuario):
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Refrigerante", internal_code=f"P{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("7.00"),
    )
    metodo = PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Dinheiro", method_type=PaymentMethod.TYPE_CASH,
    )
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])

    def vender(quantos):
        for _ in range(quantos):
            pedido = create_order(
                restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=usuario,
            )
            add_order_item(order=pedido, product=produto, quantity=1, user=usuario)
            pedido.refresh_from_db()
            register_payment(order=pedido, user=usuario, payment_method_id=metodo.id, amount=pedido.total)

    return vender


def _consultas(cliente):
    with CaptureQueriesContext(connection) as capturadas:
        resposta = cliente.get("/api/v1/orders/?page_size=50")
    assert resposta.status_code == 200
    return len(capturadas.captured_queries)


def test_listar_pedidos_custa_o_mesmo_com_2_ou_com_8(api_client, account, restaurant, branch, manager_user):
    vender = _vendedor(restaurant, branch, account, manager_user)
    vender(2)
    com_dois = _consultas(api_client)
    vender(6)
    com_oito = _consultas(api_client)

    assert com_oito == com_dois, f"{com_dois} consultas com 2 pedidos, {com_oito} com 8"


def _views_da_api():
    from django.urls import get_resolver

    vistas = set()

    def varrer(padroes):
        for padrao in padroes:
            if hasattr(padrao, "url_patterns"):
                varrer(padrao.url_patterns)
                continue
            classe = getattr(getattr(padrao, "callback", None), "cls", None)
            if classe is not None:
                vistas.add(classe)

    varrer(get_resolver().url_patterns)
    return vistas


def test_nenhum_prefetch_nasce_vazio_no_import():
    """`Prefetch(queryset=Model.objects...)` no corpo da classe é montado no IMPORT.

    Ali não há conta corrente, o TenantManager devolve `none()`, e o prefetch
    fica vazio para sempre: o caixa aparecia sem sessão aberta e a tabela de
    desconto sem regras. Enquanto o mixin jogava o prefetch fora, o defeito
    ficava escondido pelo caminho sem cache.
    """
    from django.db.models import Prefetch

    vazios = []
    for vista in _views_da_api():
        queryset = getattr(vista, "queryset", None)
        for lookup in getattr(queryset, "_prefetch_related_lookups", ()):
            if isinstance(lookup, Prefetch) and lookup.queryset is not None and lookup.queryset.query.is_empty():
                vazios.append(f"{vista.__module__}.{vista.__name__}: {lookup.prefetch_through}")
    assert vazios == []
