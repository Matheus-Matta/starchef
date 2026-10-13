"""A venda inteira não pode custar ~19 consultas POR ITEM.

Na nuvem cada consulta custa ~6 ms de rede até o banco. Com o pedido
recalculado a cada item e o restaurante relido três vezes por item, uma venda
de 10 itens fazia 219 consultas só para ABRIR a tela de pagamento (simular) e
248 para concluir: 1,5 a 3 s no caixa, com o cliente esperando.
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.orders.tests.test_venda_inteira import URL, _venda

pytestmark = pytest.mark.django_db

#: Consultas que cada item A MAIS pode custar (lock, produto, preço, insert,
#: auditoria). Eram 19 antes da validação em lote.
POR_ITEM = 5


def _consultas(api_client, corpo):
    with CaptureQueriesContext(connection) as ctx:
        resposta = api_client.post(URL, corpo, format="json")
    assert resposta.status_code in (200, 201), resposta.content
    return len(ctx.captured_queries)


@pytest.mark.parametrize("simular", [True, False])
def test_cada_item_a_mais_custa_poucas_consultas(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro, simular
):
    def corpo(itens):
        venda = _venda(restaurant, produto, dinheiro, itens=itens, valor=f"{25 * itens}.00")
        return dict(venda, simular=True, payments=[]) if simular else venda

    duas = _consultas(api_client, corpo(2))
    dez = _consultas(api_client, corpo(10))

    assert (dez - duas) / 8 <= POR_ITEM, f"{(dez - duas) / 8:.1f} consultas por item"
