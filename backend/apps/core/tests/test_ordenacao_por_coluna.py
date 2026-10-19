"""Clicar no título da coluna ordena TODOS os registros, não só a página.

O defeito: cada lista aceitava ordenar por poucos campos (`ordering_fields`).
Clicar em "Cliente" ou "Status" nos pedidos mandava `?ordering=customer_name`,
o servidor ignorava em silêncio, e a tabela reordenava só as 25 linhas da
página — o "Z" da página 1 vinha antes do "A" da página 2.
"""
import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.customers.models import Customer
from apps.orders.models import Order
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db
URL = "/api/v1/orders/"


@pytest.fixture
def pedidos(api_client, account, restaurant, branch, manager_user):
    """Sete pedidos, criados FORA da ordem alfabética dos clientes."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
    for nome, status in [("Marina", "open"), ("Ana", "paid"), ("Zeca", "open"), ("Bruno", "paid"),
                         ("Carla", "open"), ("Yara", "paid"), ("Diego", "open")]:
        cliente = Customer.objects.create(account=account, restaurant=restaurant, name=nome,
                                          phone=f"1199{len(nome)}{ord(nome[0])}")
        pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                              user=manager_user, customer_id=cliente.pk)
        Order.all_objects.filter(pk=pedido.pk).update(status=status)
    return api_client


def _todas_as_paginas(cliente, ordering, por_pagina=3):
    linhas, pagina = [], 1
    while True:
        dados = cliente.get(URL, {"ordering": ordering, "page_size": por_pagina, "page": pagina}).data
        linhas += dados["results"]
        if not dados["next"]:
            return linhas, dados
        pagina += 1


def test_ordenar_por_cliente_vale_para_todas_as_paginas(pedidos):
    linhas, _ = _todas_as_paginas(pedidos, "customer_name")

    nomes = [linha["customer_name"] for linha in linhas]
    assert nomes == sorted(nomes), nomes


def test_ordem_decrescente_tambem_atravessa_as_paginas(pedidos):
    linhas, _ = _todas_as_paginas(pedidos, "-customer_name")

    nomes = [linha["customer_name"] for linha in linhas]
    assert nomes == sorted(nomes, reverse=True), nomes


def test_empate_de_status_nao_repete_nem_pula_pedido_entre_paginas(pedidos):
    """Quatro pedidos "open": sem desempate, a paginação por OFFSET podia
    mostrar o mesmo pedido em duas páginas e sumir com outro."""
    linhas, _ = _todas_as_paginas(pedidos, "status", por_pagina=2)

    ids = [linha["id"] for linha in linhas]
    assert len(ids) == len(set(ids)) == 7
    status = [linha["status"] for linha in linhas]
    assert status == sorted(status)


def test_a_lista_diz_quais_colunas_o_servidor_sabe_ordenar(pedidos):
    """A tabela usa isto para não oferecer ordenação que não ordenaria nada."""
    ordenaveis = pedidos.get(URL).data["orderable"]

    assert {"customer_name", "status", "total", "sequence", "table_number"} <= set(ordenaveis)
    assert "command_label" not in ordenaveis  # calculada: não existe no banco


@pytest.mark.parametrize("pedido_errado", ["coluna_que_nao_existe", "-", "status;drop table", ""])
def test_ordenacao_invalida_e_ignorada_sem_erro(pedidos, pedido_errado):
    resposta = pedidos.get(URL, {"ordering": pedido_errado})

    assert resposta.status_code == 200
    assert resposta.data["count"] == 7


def test_campo_que_a_tela_nao_mostra_nao_pode_ordenar(api_client, admin_user):
    """Ordenar usuários pela senha revelaria a ordem dos hashes: só ordena
    pelo que a própria lista já mostra."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(admin_user)}")

    dados = api_client.get("/api/v1/users/", {"ordering": "password"}).data

    assert "password" not in dados["orderable"]
