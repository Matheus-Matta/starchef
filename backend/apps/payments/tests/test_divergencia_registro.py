"""Registrar a divergência de vendas: o dinheiro que entrou sem venda no PDV.

Não é pedido, não é venda e não é NFC-e — é o registro administrativo da
diferença, para a conciliação e para o contador decidir a regularização.
"""
from decimal import Decimal

import pytest

from apps.orders.models import Order
from apps.payments.discrepancy import SalesDiscrepancy
from apps.payments.tests.conftest import URL, corpo

pytestmark = pytest.mark.django_db


def test_registra_com_total_calculado_no_servidor(api_client, sessao_de_caixa, forma):
    sessao = sessao_de_caixa()
    pix, cartao = forma("PIX"), forma("Cartão", "card")

    resposta = api_client.post(URL, corpo(sessao, (pix, "2000.00"), (cartao, "1000.50")), format="json")

    assert resposta.status_code == 201, resposta.content
    assert Decimal(resposta.data["amount"]) == Decimal("3000.50")
    assert resposta.data["status"] == "open"
    nomes = {f["name"]: f["amount"] for f in resposta.data["payment_methods"]}
    assert nomes == {"PIX": "2000.00", "Cartão": "1000.50"}
    linha = SalesDiscrepancy.all_objects.get()
    assert (linha.restaurant_id, linha.branch_id) == (sessao.restaurant_id, sessao.branch_id)


def test_nao_cria_pedido_nem_venda(api_client, sessao_de_caixa, forma):
    """O ponto da funcionalidade: nada de "pedido fictício" para fechar a conta."""
    pedidos_antes = Order.all_objects.count()

    api_client.post(URL, corpo(sessao_de_caixa(), (forma("PIX"), "500.00")), format="json")

    assert Order.all_objects.count() == pedidos_antes


def test_total_enviado_pelo_cliente_e_ignorado(api_client, sessao_de_caixa, forma):
    dados = corpo(sessao_de_caixa(), (forma("PIX"), "10.00"))
    dados["amount"] = "999999.99"

    resposta = api_client.post(URL, dados, format="json")

    assert Decimal(resposta.data["amount"]) == Decimal("10.00")


@pytest.mark.parametrize(
    "valor",
    ["0", "-5.00", "10.005", "abc", None],
    ids=["zero", "negativo", "tres-casas", "texto", "nulo"],
)
def test_valor_invalido_e_400(api_client, sessao_de_caixa, forma, valor):
    resposta = api_client.post(URL, corpo(sessao_de_caixa(), (forma("PIX"), valor)), format="json")

    assert resposta.status_code == 400, resposta.content
    assert not SalesDiscrepancy.all_objects.exists()


def test_sem_forma_sem_motivo_e_forma_repetida_sao_400(api_client, sessao_de_caixa, forma):
    sessao, pix = sessao_de_caixa(), forma("PIX")
    sem_forma = corpo(sessao)
    sem_motivo = corpo(sessao, (pix, "1.00")) | {"reason": "   "}
    repetida = corpo(sessao, (pix, "1.00"), (pix, "2.00"))

    for dados in (sem_forma, sem_motivo, repetida):
        assert api_client.post(URL, dados, format="json").status_code == 400

    assert not SalesDiscrepancy.all_objects.exists()


@pytest.mark.parametrize("bruto", [[], "texto", 42, ["lista"]], ids=["lista", "texto", "numero", "lista-texto"])
def test_corpo_torto_do_cliente_e_400_e_nao_500(api_client, bruto):
    resposta = api_client.post(URL, bruto, format="json")

    assert resposta.status_code == 400


def test_forma_de_outra_conta_nao_entra(api_client, sessao_de_caixa, admin_user):
    from apps.accounts.models import Account
    from apps.payments.models import PaymentMethod
    from apps.restaurants.models import Branch, Restaurant

    outra = Account.objects.create(name="Outra")
    loja = Restaurant.all_objects.create(account=outra, legal_name="O LTDA", trade_name="O")
    alheia = PaymentMethod.all_objects.create(
        account=outra, restaurant=loja, branch=Branch.all_objects.filter(restaurant=loja).first(),
        name="PIX alheio", method_type="pix", created_by=admin_user, updated_by=admin_user,
    )

    resposta = api_client.post(URL, corpo(sessao_de_caixa(), (alheia, "5.00")), format="json")

    assert resposta.status_code == 400
    assert "PIX alheio" not in resposta.content.decode()


def test_operador_de_caixa_nao_registra(caixa_client, sessao_de_caixa, forma):
    """Registrar é gesto gerencial: é perda no relatório e evidência fiscal."""
    resposta = caixa_client.post(URL, corpo(sessao_de_caixa(), (forma("PIX"), "5.00")), format="json")

    assert resposta.status_code == 403
    assert caixa_client.get(URL).status_code == 403


def test_nao_se_apaga_cancela_se(api_client, sessao_de_caixa, forma):
    criada = api_client.post(URL, corpo(sessao_de_caixa(), (forma("PIX"), "5.00")), format="json")

    resposta = api_client.delete(f"{URL}{criada.data['id']}/")

    assert resposta.status_code == 405
    assert SalesDiscrepancy.all_objects.count() == 1


def test_edita_so_enquanto_aberta_e_nao_troca_de_sessao(api_client, sessao_de_caixa, forma):
    sessao, pix = sessao_de_caixa(), forma("PIX")
    criada = api_client.post(URL, corpo(sessao, (pix, "5.00")), format="json").data
    alvo = f"{URL}{criada['id']}/"

    editada = api_client.patch(alvo, {"by_payment_method": [{"payment_method": str(pix.pk), "amount": "7.25"}]},
                               format="json")
    assert Decimal(editada.data["amount"]) == Decimal("7.25")
    outra = sessao_de_caixa(station="Caixa 2")
    assert api_client.patch(alvo, {"cash_register": str(outra.pk)}, format="json").status_code == 400

    api_client.post(f"{alvo}review/", {}, format="json")
    assert api_client.patch(alvo, {"notes": "x"}, format="json").status_code == 409
