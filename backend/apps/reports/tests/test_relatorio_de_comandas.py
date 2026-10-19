"""O relatório de comandas: o salão AGORA e o que as comandas fizeram no período.

Os cenários são os do salão de verdade: comanda em uso, conta aberta e
esquecida segurando o cartão, item lançado errado e cancelado pelo garçom, a
mesma comanda usada duas vezes no dia, a conta cancelada (consumo que virou
perda) e o filtro de data digitado ao contrário.
"""
import uuid
from decimal import Decimal

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.menu.models import Product
from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem, Order
from apps.orders.services import cancel_order, create_order
from apps.payments.models import PaymentMethod
from apps.payments.services import register_payment
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db
URL = "/api/v1/reports/commands/"


@pytest.fixture
def salao(account, restaurant, branch, manager_user, api_client):
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="Chopp", internal_code=f"C{uuid.uuid4().hex[:6]}",
                                     sale_price=Decimal("25.00"))
    dinheiro = PaymentMethod.objects.create(account=account, restaurant=restaurant, branch=branch,
                                            name="Dinheiro", method_type=PaymentMethod.TYPE_CASH)
    comandas = {n: Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                          number=n) for n in (1, 2, 3, 4)}
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    def lancar(numero, vezes=1):
        return [launch_item(command=comandas[numero], product=produto, user=manager_user)
                for _ in range(vezes)]

    def conta(*numeros):
        pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND,
                              user=manager_user)
        attach_commands_to_order(order=pedido, command_ids=[comandas[n].pk for n in numeros],
                                 user=manager_user)
        pedido.refresh_from_db()
        return pedido

    def pagar(*numeros):
        pedido = conta(*numeros)
        register_payment(order=pedido, user=manager_user, payment_method_id=dinheiro.pk,
                         amount=pedido.total)
        return pedido

    def ler(**filtros):
        return api_client.get(URL, filtros)

    return type("Salao", (), {"lancar": staticmethod(lancar), "conta": staticmethod(conta),
                              "pagar": staticmethod(pagar), "ler": staticmethod(ler),
                              "user": manager_user})


def test_o_salao_agora_separa_em_uso_livre_e_presa_em_conta_aberta(salao):
    salao.lancar(1, vezes=2)          # comanda 1: dois chopps, ninguém pagou
    salao.lancar(2)
    salao.conta(2)                    # comanda 2: anexada a uma conta que ficou aberta
    salao.lancar(3)
    salao.pagar(3)                    # comanda 3: paga, livre de novo

    agora = salao.ler().data["now"]

    assert agora["registered"] == 4
    assert agora["in_use"] == 2
    assert agora["free"] == 2
    assert agora["in_open_bill"] == 1
    assert Decimal(str(agora["in_use_total"])) == Decimal("75.00")
    assert agora["in_use_items"] == 3


def test_a_lista_de_comandas_em_uso_diz_quanto_cada_uma_deve(salao):
    salao.lancar(1, vezes=2)
    salao.lancar(2)
    salao.conta(2)

    linhas = {linha["number"]: linha for linha in salao.ler().data["open_commands"]}

    assert set(linhas) == {1, 2}
    assert Decimal(str(linhas[1]["total"])) == Decimal("50.00") and linhas[1]["items"] == 2
    assert linhas[1]["in_open_bill"] is False and linhas[2]["in_open_bill"] is True
    assert linhas[1]["open_since"]


def test_item_cancelado_pelo_garcom_nao_conta_como_consumo(salao):
    """O garçom lançou na comanda errada e cancelou: a comanda 4 não deve nada
    e precisa aparecer LIVRE, senão o caixa procura uma conta que não existe."""
    (errado,) = salao.lancar(4)
    errado.status = CommandItem.STATUS_CANCELLED
    errado.save(update_fields=["status"])

    agora = salao.ler().data["now"]

    assert agora["in_use"] == 0
    assert Decimal(str(agora["in_use_total"])) == Decimal("0.00")


def test_no_periodo_conta_pagas_ticket_usadas_e_reuso_da_mesma_comanda(salao):
    salao.lancar(1, vezes=2)
    salao.pagar(1)                    # 1ª vez da comanda 1: R$ 50
    salao.lancar(1)
    salao.pagar(1)                    # a mesma comanda, outro cliente: R$ 25
    salao.lancar(2)
    salao.pagar(2)                    # R$ 25
    salao.lancar(3)                   # usada e ainda aberta

    dados = salao.ler().data
    periodo = dados["period"]

    assert periodo["paid"] == 3
    assert Decimal(str(periodo["paid_total"])) == Decimal("100.00")
    assert Decimal(str(periodo["average_ticket"])) == Decimal("33.33")
    assert periodo["used"] == 3
    assert periodo["launched_items"] == 5
    por_comanda = {linha["number"]: linha for linha in dados["by_command"]}
    assert por_comanda[1]["uses"] == 2
    assert Decimal(str(por_comanda[1]["total"])) == Decimal("75.00")


def test_conta_cancelada_vira_perda_e_nao_venda(salao):
    salao.lancar(1, vezes=2)
    pedido = salao.conta(1)
    cancel_order(pedido, salao.user, "Cliente saiu sem pagar a conta")

    periodo = salao.ler().data["period"]

    assert periodo["paid"] == 0
    assert periodo["lost_items"] == 2
    assert Decimal(str(periodo["lost_total"])) == Decimal("50.00")


@pytest.mark.parametrize("filtros", [
    {"date_from": "2026-10-20", "date_to": "2026-10-01"},   # datas ao contrário
    {"date_from": "18/10/2026"},                             # formato brasileiro digitado
])
def test_periodo_digitado_errado_e_recusado_com_motivo(salao, filtros):
    resposta = salao.ler(**filtros)

    assert resposta.status_code == 400
    assert "data" in str(resposta.data).lower() or "período" in str(resposta.data).lower()


def test_periodo_sem_movimento_responde_zerado_sem_dividir_por_zero(salao):
    periodo = salao.ler(date_from="2020-01-01", date_to="2020-01-02").data["period"]

    assert periodo["paid"] == 0
    assert Decimal(str(periodo["average_ticket"])) == Decimal("0.00")
    assert periodo["average_stay_minutes"] is None


def test_gerente_de_outro_restaurante_nao_ve_as_comandas_daqui(salao, account, branch):
    from django.contrib.auth.models import User
    from rest_framework.test import APIClient

    from apps.accounts.models import UserProfile
    from apps.accounts.role_catalog import ensure_system_roles
    from apps.restaurants.models import Restaurant

    salao.lancar(1)
    outro = Restaurant.objects.create(account=account, trade_name="Filial 2", legal_name="F2",
                                      cnpj="2" * 14)
    gerente = User.objects.create_user(username="outro", password="x")
    UserProfile.objects.create(user=gerente, account=account, restaurant=outro,
                               role=ensure_system_roles(account)["manager"])
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(gerente)}")

    agora = cliente.get(URL).data["now"]

    assert agora["in_use"] == 0 and agora["registered"] == 0


def test_exporta_csv_das_comandas_em_uso(salao):
    salao.lancar(1, vezes=2)

    resposta = salao.ler(export="csv")

    assert resposta["Content-Type"].startswith("text/csv")
    texto = resposta.content.decode()
    assert "Comanda" in texto and "50.00" in texto
