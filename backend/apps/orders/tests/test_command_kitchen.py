"""A comanda manda para a cozinha do mesmo jeito que o pedido."""
import pytest
from django.core.exceptions import ValidationError

from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_items import launch_item
from apps.orders.command_kitchen import send_command_to_kitchen, void_command_item
from apps.orders.models import CommandItem, Order
from apps.restaurants.models import Command


def _comanda(restaurant, branch, numero):
    return Command.objects.create(
        account=restaurant.account, restaurant=restaurant, branch=branch,
        number=numero, code=f"CMD-{numero:04d}",
    )


@pytest.mark.django_db
def test_enviar_a_comanda_a_cozinha_marca_os_itens(restaurant, branch, manager_user, produto):
    comanda = _comanda(restaurant, branch, 30)
    item = launch_item(command=comanda, product=produto, user=manager_user)

    lote = send_command_to_kitchen(comanda, manager_user)

    item.refresh_from_db()
    assert item.batch_id == lote.pk
    # Sem carência configurada a rodada sai na hora.
    assert item.status == CommandItem.STATUS_SENT
    assert item.sent_to_kitchen_at is not None


@pytest.mark.django_db
def test_sem_item_pendente_nao_manda_rodada_vazia(restaurant, branch, manager_user):
    comanda = _comanda(restaurant, branch, 31)
    with pytest.raises(ValidationError):
        send_command_to_kitchen(comanda, manager_user)


@pytest.mark.django_db
def test_o_item_do_pedido_HERDA_o_envio_e_nao_reenvia(
    restaurant, branch, manager_user, produto
):
    """O prato saiu às 20h; a conta fecha às 22h.

    Se o item do pedido nascesse pendente, ele voltaria para o forno — e o
    cliente receberia a picanha duas vezes.
    """
    from apps.orders.services import create_order

    comanda = _comanda(restaurant, branch, 32)
    anotacao = launch_item(command=comanda, product=produto, user=manager_user)
    send_command_to_kitchen(comanda, manager_user)
    anotacao.refresh_from_db()

    pedido = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user
    )
    criados = attach_commands_to_order(
        order=pedido, command_ids=[comanda.pk], user=manager_user
    )

    item = criados[0]
    assert item.status == anotacao.status == CommandItem.STATUS_SENT
    assert item.sent_to_kitchen_at == anotacao.sent_to_kitchen_at


@pytest.mark.django_db
def test_cancelar_anotacao_tira_da_comanda_como_perda(
    restaurant, branch, manager_user, produto
):
    comanda = _comanda(restaurant, branch, 33)
    item = launch_item(command=comanda, product=produto, user=manager_user)

    void_command_item(item, user=manager_user, reason="Cliente desistiu")

    item.refresh_from_db()
    assert item.status == CommandItem.STATUS_CANCELLED
    # Perda, não venda: é a distinção que o fechamento do mês precisa.
    assert item.command_status == CommandItem.STATUS_CANCELADO


@pytest.mark.django_db
def test_cancelamento_exige_motivo(restaurant, branch, manager_user, produto):
    comanda = _comanda(restaurant, branch, 34)
    item = launch_item(command=comanda, product=produto, user=manager_user)
    with pytest.raises(ValidationError):
        void_command_item(item, user=manager_user, reason="")
