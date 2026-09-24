"""O que cada conflito de banco SIGNIFICA para quem está no balcão.

Toda violação de unicidade virava a mesma frase — "já existe um registro com
estes dados" —, que não diz o que o operador fez, em qual registro, nem o que
fazer a seguir. Ele relê a tela, repete o gesto, e chega o mesmo erro.

Aqui ficam as restrições que ele ENCOSTA na prática. O que não estiver nesta
lista continua caindo na frase geral: é melhor uma frase vaga do que uma
específica e errada.

## Por que cada entrada tem DUAS formas de ser reconhecida

Os dois bancos contam a mesma violação de jeitos diferentes:

    PostgreSQL: duplicate key value violates unique constraint
                "unique_customer_group_per_account"
    SQLite:     UNIQUE constraint failed:
                customers_customergroup.account_id, customers_customergroup.name

Reconhecer só o nome da restrição fazia este catálogo inteiro ficar INERTE em
desenvolvimento e nos testes — e inerte em silêncio, porque a frase geral
continua saindo e ninguém nota que a específica nunca apareceu. Por isso cada
entrada lista também a coluna que o SQLite cita.
"""

#: Cada item: (fragmentos reconhecíveis, o que dizer ao operador).
#:
#: Basta UM fragmento aparecer na mensagem do banco. O primeiro é o nome da
#: restrição (PostgreSQL); os seguintes são a tabela e a coluna que o SQLite
#: cita, o suficiente para não confundir com outra restrição da mesma tabela.
CONFLITOS_CONHECIDOS = (
    (
        ("unique_order_sequence_by_branch", "orders_order.sequence"),
        "Este número de pedido já existe. Se isso se repetir, dois servidores "
        "podem estar numerando na mesma faixa — confira `SYNC_NODE_TYPE` (a "
        "loja usa `local`, o servidor central usa `cloud`).",
    ),
    (
        ("unique_order_item_per_command_item", "orderitem.command_item_id"),
        "Esta anotação da comanda já está em uma conta. Remova o cartão "
        "daquela conta antes de cobrá-lo aqui.",
    ),
    (
        ("unique_customer_group_per_account", "customergroup.name"),
        "Já existe um grupo de clientes com este nome. Dois grupos com o "
        "mesmo nome viram duas listas que ninguém consegue distinguir depois.",
    ),
    (
        ("unique_command_number_by_restaurant", "command.number"),
        "Já existe uma comanda com este número neste restaurante.",
    ),
    (
        ("unique_command_code_by_restaurant", "command.code"),
        "Já existe uma comanda com este código neste restaurante.",
    ),
    (
        ("unique_table_number_by_branch", "table.number"),
        "Já existe uma mesa com este número nesta filial.",
    ),
    (
        ("unique_printer_by_branch", "printer.name"),
        "Já existe uma impressora com este nome nesta filial.",
    ),
)


def mensagem_para(texto):
    """A frase do conflito reconhecido, ou `None` para cair na frase geral."""
    for fragmentos, mensagem in CONFLITOS_CONHECIDOS:
        if any(fragmento in texto for fragmento in fragmentos):
            return mensagem
    return None
