"""O estado da mesa que a lista mostra é o mesmo que o detalhe mostra.

O DEFEITO: `Table.status` é uma coluna, e um desvínculo que não a limpou deixa
`occupied` para sempre. A lista lia a coluna e desenhava **Ocupada**; o detalhe
contava os cartões vinculados e dizia **livre**. Mesma mesa, um clique de
diferença, e o garçom sem saber em qual acreditar.

A regra é a que a própria tela anuncia: a mesa fica ocupada enquanto houver
comanda vinculada. `reserved` e `cleaning` são decisão de pessoa e continuam
na coluna.
"""
import pytest

from apps.restaurants.models import Command, Table, TableSector

pytestmark = pytest.mark.django_db


@pytest.fixture
def mesa(account, restaurant, branch):
    setor = TableSector.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Salão"
    )
    return Table.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sector=setor,
        number="12",
        capacity=4,
    )


def _status(client, mesa):
    resposta = client.get(f"/api/v1/tables/{mesa.id}/")
    assert resposta.status_code == 200, resposta.data
    return resposta.data["status"]


def test_occupied_orfao_na_coluna_volta_a_livre(admin_client, mesa):
    # Nenhum cartão sentado: a coluna está mentindo, e era ela que a lista lia.
    Table.all_objects.filter(pk=mesa.pk).update(status=Table.STATUS_OCCUPIED)

    assert _status(admin_client, mesa) == Table.STATUS_FREE


def test_mesa_com_comanda_vinculada_responde_ocupada(
    admin_client, account, restaurant, branch, mesa
):
    Command.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        number="7",
        current_table=mesa,
    )

    assert _status(admin_client, mesa) == Table.STATUS_OCCUPIED


def test_mesa_livre_com_cartao_sentado_nao_e_desenhada_livre(
    admin_client, account, restaurant, branch, mesa
):
    # O outro sentido, que já valia: coluna atrasada em `free` não pode apagar
    # um cartão que está na mesa.
    Table.all_objects.filter(pk=mesa.pk).update(status=Table.STATUS_FREE)
    Command.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        number="8",
        current_table=mesa,
    )

    assert _status(admin_client, mesa) == Table.STATUS_OCCUPIED


@pytest.mark.parametrize("estado", [Table.STATUS_RESERVED, Table.STATUS_CLEANING])
def test_reserva_e_limpeza_sobrevivem_sem_comanda(admin_client, mesa, estado):
    # Os dois não são consequência do consumo: derivá-los do vínculo apagaria a
    # reserva de uma mesa que ainda não recebeu ninguém.
    Table.all_objects.filter(pk=mesa.pk).update(status=estado)

    assert _status(admin_client, mesa) == estado
