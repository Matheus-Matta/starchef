"""Entrada errada do cliente vira 4xx com mensagem — nunca 500.

Cada caso aqui reproduz um defeito que o teste de carga
(`docs/TESTE_CARGA.md`) encontrou em produção-simulada: um campo ausente, um
texto num campo de dinheiro, uma referência de outro restaurante. Todos
devolviam "Ocorreu um erro interno".

O 500 não é só feio: o PDV trata 5xx como falha TEMPORÁRIA e devolve a
operação à fila para tentar de novo indefinidamente, em vez de mandá-la para a
tela de revisão. Um erro de digitação virava uma venda presa para sempre.
"""
import pytest
from rest_framework import status
from rest_framework_simplejwt.tokens import AccessToken

from apps.payments.models import PaymentMethod

pytestmark = pytest.mark.django_db


@pytest.fixture
def cliente(api_client, manager_user):
    """Token real no header: o `TenantMiddleware` autentica ANTES do DRF.

    `force_authenticate` não serve — ele age na camada do DRF, e a requisição
    já teria sido barrada com 401 pelo middleware.
    """
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )
    return api_client


@pytest.fixture
def order(cliente, restaurant, branch):
    criado = cliente.post(
        "/api/v1/orders/",
        {"restaurant": str(restaurant.id), "order_type": "counter"},
        format="json",
    )
    assert criado.status_code == status.HTTP_201_CREATED, criado.data
    # Devolve o ID e não a instância: reler pelo ORM aqui exigiria o contexto
    # de tenant, e o que os testes precisam é só a rota do pedido.
    return criado.data["id"]


@pytest.fixture
def produto(product, restaurant):
    """O `product` de `tests/conftest.py`, disponível no restaurante do teste."""
    product.restaurants.add(restaurant)
    return product


def _e_erro_de_cliente(resposta):
    """400 ou 404 — o que não pode é 5xx nem um 2xx silencioso."""
    return 400 <= resposta.status_code < 500


class TestLancamentoDeItem:
    def test_item_sem_produto_recusa(self, cliente, order):
        resposta = cliente.post(
            f"/api/v1/orders/{order}/items/", {"quantity": 1}, format="json"
        )
        assert _e_erro_de_cliente(resposta), resposta.data

    def test_produto_inexistente_recusa(self, cliente, order):
        resposta = cliente.post(
            f"/api/v1/orders/{order}/items/",
            {"product": "11111111-2222-3333-4444-555555555555", "quantity": 1},
            format="json",
        )
        assert _e_erro_de_cliente(resposta), resposta.data

    def test_produto_com_id_que_nem_e_uuid_recusa(self, cliente, order):
        resposta = cliente.post(
            f"/api/v1/orders/{order}/items/",
            {"product": "nao-e-uuid", "quantity": 1},
            format="json",
        )
        assert _e_erro_de_cliente(resposta), resposta.data

    @pytest.mark.parametrize("quantidade", ["duas", 0, -3, 10**30])
    def test_quantidade_invalida_recusa(self, cliente, order, produto, quantidade):
        resposta = cliente.post(
            f"/api/v1/orders/{order}/items/",
            {"product": str(produto.id), "quantity": quantidade},
            format="json",
        )
        assert _e_erro_de_cliente(resposta), (quantidade, resposta.data)


class TestFechamento:
    def test_desconto_em_texto_recusa(self, cliente, order):
        resposta = cliente.post(
            f"/api/v1/orders/{order}/close/", {"discount": "dez reais"}, format="json"
        )
        assert _e_erro_de_cliente(resposta), resposta.data

    def test_desconto_negativo_recusa(self, cliente, order):
        """Negativo passava pela guarda `> 0` e AUMENTAVA o total do pedido."""
        resposta = cliente.post(
            f"/api/v1/orders/{order}/close/", {"discount": -50}, format="json"
        )
        assert _e_erro_de_cliente(resposta), resposta.data

    def test_desconto_maior_que_o_subtotal_recusa(self, cliente, order, produto):
        cliente.post(
            f"/api/v1/orders/{order}/items/",
            {"product": str(produto.id), "quantity": 1},
            format="json",
        )
        resposta = cliente.post(
            f"/api/v1/orders/{order}/close/", {"discount": 999999}, format="json"
        )
        assert _e_erro_de_cliente(resposta), resposta.data


class TestRecebimento:
    @pytest.fixture
    def forma(self, account, restaurant):
        return PaymentMethod.objects.create(
            account=account, restaurant=restaurant, name="Dinheiro", method_type="cash"
        )

    def test_sem_forma_de_pagamento_recusa(self, cliente, order, forma):
        resposta = cliente.post(
            f"/api/v1/orders/{order}/pay/", {"amount": "10.00"}, format="json"
        )
        assert _e_erro_de_cliente(resposta), resposta.data

    def test_sem_valor_recusa(self, cliente, order, forma):
        resposta = cliente.post(
            f"/api/v1/orders/{order}/pay/",
            {"payment_method": str(forma.id)},
            format="json",
        )
        assert _e_erro_de_cliente(resposta), resposta.data

    def test_valor_em_texto_recusa(self, cliente, order, forma):
        resposta = cliente.post(
            f"/api/v1/orders/{order}/pay/",
            {"payment_method": str(forma.id), "amount": "vinte reais"},
            format="json",
        )
        assert _e_erro_de_cliente(resposta), resposta.data

    def test_forma_inexistente_recusa(self, cliente, order):
        resposta = cliente.post(
            f"/api/v1/orders/{order}/pay/",
            {
                "payment_method": "99999999-8888-7777-6666-555555555555",
                "amount": "10.00",
            },
            format="json",
        )
        assert _e_erro_de_cliente(resposta), resposta.data


class TestCorpoMalformado:
    """Uma lista no lugar do objeto quebrava `request.data.get` com 500."""

    @pytest.mark.parametrize(
        "rota",
        [
            "/api/v1/orders/",
            "/api/v1/customers/",
            "/api/v1/menu/products/",
            "/api/v1/cash-register/open/",
        ],
    )
    def test_lista_no_lugar_do_objeto_recusa(self, cliente, rota):
        resposta = cliente.post(rota, [1, 2, 3], format="json")
        assert _e_erro_de_cliente(resposta), (rota, resposta.status_code)

    def test_login_com_lista_no_corpo_recusa(self, client):
        """A rota mais exposta do sistema: ela responde sem autenticação."""
        resposta = client.post(
            "/api/v1/auth/login/", [1, 2, 3], content_type="application/json"
        )
        assert 400 <= resposta.status_code < 500, resposta.status_code


class TestNumeroAbsurdo:
    def test_inteiro_grande_demais_recusa(self, cliente, restaurant):
        """Sem faixa declarada no SQLite, 10^30 estourava no driver (500)."""
        resposta = cliente.post(
            "/api/v1/commands/",
            {"restaurant": str(restaurant.id), "number": 10**30, "code": "X1"},
            format="json",
        )
        assert _e_erro_de_cliente(resposta), resposta.data

    def test_custo_negativo_de_insumo_recusa(self, cliente, restaurant):
        resposta = cliente.post(
            "/api/v1/menu/ingredients/",
            {"name": "Farinha", "unit": "kg", "average_cost": -999.99},
            format="json",
        )
        assert _e_erro_de_cliente(resposta), resposta.data


class TestPisoNumericoPorPadrao:
    """Todo numérico gravável recusa negativo, sem cada serializer ter de
    lembrar de listar o campo. Era opt-in e 49 campos ficaram de fora."""

    def test_taxa_de_servico_negativa_recusa(self, cliente, restaurant):
        resposta = cliente.patch(
            f"/api/v1/restaurants/{restaurant.id}/",
            {"default_service_fee_percent": "-10.00"},
            format="json",
        )
        assert resposta.status_code == status.HTTP_400_BAD_REQUEST, resposta.data
        assert "default_service_fee_percent" in resposta.data["error"]["message"]

    def test_ordem_de_exibicao_negativa_recusa(self, cliente, restaurant):
        resposta = cliente.post(
            "/api/v1/menu/categories/",
            {"restaurant": str(restaurant.id), "name": "Bebidas", "display_order": -1},
            format="json",
        )
        assert resposta.status_code == status.HTTP_400_BAD_REQUEST, resposta.data
        assert "display_order" in resposta.data["error"]["message"]

    def test_campo_assinado_de_proposito_aceita_negativo(self, cliente, produto):
        resposta = cliente.post(
            "/api/v1/menu/variations/",
            {"product": str(produto.id), "name": "Sem queijo", "price_delta": "-2.00"},
            format="json",
        )
        assert resposta.status_code == status.HTTP_201_CREATED, resposta.data
        assert resposta.data["price_delta"] == "-2.00"
