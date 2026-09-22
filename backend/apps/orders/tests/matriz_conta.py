"""O cenário compartilhado das duas matrizes: um cartão, uma mesa, uma conta.

Não é um arquivo de teste — é o que os quatro arquivos de matriz montam antes
de perguntar qualquer coisa. Fica separado porque o INVARIANTE de baixo é o
mesmo para todo caminho de recebimento, e repeti-lo em quatro lugares é como
ele começa a divergir.
"""
from apps.core.tenant import tenant_context
from apps.orders.command_items import launch_item
from apps.orders.models import Order
from apps.orders.models_command_item import CommandItem
from apps.restaurants.models import Command, Table

from .conftest import anexar, criar_vazio, ler


def comanda_com_consumo(
    *, account, restaurant, branch, user, produto, mesa=None, quantidade=1
):
    """Um cartão em uso: com anotação pendente e, se houver, sentado na mesa."""
    comanda = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch, current_table=mesa
    )
    launch_item(command=comanda, product=produto, user=user, quantity=quantidade)
    if mesa is not None:
        mesa.status = Table.STATUS_OCCUPIED
        mesa.save(update_fields=["status"])
    return comanda


def abrir_conta(api, *, restaurant, cartoes):
    """A conta do caixa com estes cartões dentro. Devolve o id do pedido."""
    pedido = criar_vazio(api, restaurant=restaurant, tipo=Order.TYPE_COMMAND)
    assert pedido.status_code == 201, pedido.data
    puxou = anexar(api, pedido.data["id"], [c.pk for c in cartoes])
    assert puxou.status_code == 200, puxou.data
    return pedido.data["id"]


def anotacoes_de(cartao, **filtros):
    """As anotações do cartão — DEPOIS de uma chamada de API.

    ATENÇÃO, e isto custa caro quando se esquece: a chamada de API zera o
    contexto de tenant no fim da requisição. Toda consulta ORM feita depois
    dela volta VAZIA, e uma asserção como `.filter(...).exists() is False`
    passa sem ter verificado coisa alguma.

    `refresh_from_db()` escapa porque usa o manager base; um `filter` do
    `TenantManager`, não. Por isso toda leitura pós-chamada entra por aqui.
    """
    with tenant_context(cartao.account):
        return set(
            CommandItem.objects.filter(command=cartao, **filtros).values_list(
                "command_status", flat=True
            )
        )


def conferir_tudo_fechado(api, conta_id, *, cartao, mesa):
    """Os QUATRO invariantes de uma conta recebida por inteiro.

    Receber mexe em quatro coisas ao mesmo tempo, e quando uma fica para trás
    o sintoma aparece longe dali: o cartão que reaparece cheio no cliente
    seguinte, a mesa ocupada sem ninguém sentado. Conferir só o status do
    pedido deixaria os outros três passarem.
    """
    assert ler(api, conta_id)["status"] == Order.STATUS_PAID
    cartao.refresh_from_db()
    mesa.refresh_from_db()
    assert cartao.status == Command.STATUS_FREE, "o cartão continua ocupado"
    assert cartao.current_table_id is None, "o cartão pago continua sentado na mesa"
    assert mesa.status == Table.STATUS_FREE, "a mesa ficou presa"
    estados = anotacoes_de(cartao)
    assert estados, "nenhuma anotação encontrada: a conferência seria vazia"
    assert CommandItem.STATUS_PENDENTE not in estados, (
        "as anotações seguem pendentes: seriam cobradas de novo"
    )
    assert estados == {CommandItem.STATUS_COBRADO}, (
        f"pago tem de sair como VENDA, e saiu como {estados}"
    )
