"""As duas rotas que a página de comandas chama ao abrir.

A tela ficava parada, e "parada" pode ser três coisas muito diferentes: a rota
não existe, ela recusa, ou ela responde e o cliente não sabe ler. Estes testes
descartam a primeira e a segunda de uma vez — o que sobrar é do lado do
cliente, e é lá que se procura.
"""
import pytest

from apps.restaurants.models import Command


@pytest.mark.django_db
def test_a_lista_que_a_tela_pede_responde_paginada(api_client, restaurant, branch):
    Command.objects.create(
        account=restaurant.account,
        restaurant=restaurant,
        branch=branch,
        number=13,
        code="C013",
    )

    resposta = api_client.get("/api/v1/commands/", {"page_size": 200, "is_active": "true"})

    assert resposta.status_code == 200
    # A tela lê `results`: uma resposta sem envelope de paginação deixaria a
    # lista vazia sem erro nenhum, que é o formato de falha mais difícil de
    # diagnosticar no balcão.
    assert "results" in resposta.data
    assert [c["number"] for c in resposta.data["results"]] == [13]


@pytest.mark.django_db
def test_os_itens_de_uma_comanda_vazia_respondem_em_vez_de_recusar(
    api_client, restaurant, branch
):
    """Comanda livre não é erro: é uma comanda sem item.

    Recusar aqui faria o painel da direita mostrar falha para o caso mais
    comum do salão — um cartão que ninguém usou ainda.
    """
    comanda = Command.objects.create(
        account=restaurant.account,
        restaurant=restaurant,
        branch=branch,
        number=14,
        code="C014",
    )

    resposta = api_client.get(f"/api/v1/commands/{comanda.id}/items/")

    assert resposta.status_code == 200
    assert resposta.data["items"] == []
    # "Em uso" é ter anotação PENDENTE, e não um campo de estado: a listagem
    # traz a contagem para a grade não precisar abrir cada cartão.
    assert resposta.data["command"]["pending_items"] == 0
