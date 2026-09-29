"""A lista que o caixa lê antes de cobrar uma comanda."""

import pytest

from apps.orders.command_items import launch_item, open_items_of_command
from apps.orders.models import CommandItem
from apps.restaurants.models import Command


@pytest.mark.django_db
def test_lista_da_comanda_mostra_somente_o_que_entra_no_pagamento(
    restaurant, branch, manager_user, produto
):
    """Cancelado e cortesia não podem reaparecer no carrinho do caixa.

    O fechamento já ignorava essas linhas, mas a rota de leitura devolvia
    qualquer anotação com `command_status=pending`. Assim o PDV mostrava e
    somava na tela itens que o servidor corretamente não cobraria.
    """
    comanda = Command.objects.create(
        account=restaurant.account,
        restaurant=restaurant,
        branch=branch,
        number=34,
        code="CMD-0034",
    )
    cobravel = launch_item(command=comanda, product=produto, user=manager_user)
    cancelado = launch_item(command=comanda, product=produto, user=manager_user)
    cortesia = launch_item(command=comanda, product=produto, user=manager_user)
    cancelado.status = CommandItem.STATUS_CANCELLED
    cancelado.save(update_fields=["status"])
    cortesia.status = CommandItem.STATUS_COMPED
    cortesia.save(update_fields=["status"])

    assert list(open_items_of_command(comanda.pk)) == [cobravel]
