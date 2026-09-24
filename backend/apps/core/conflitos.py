"""O que cada conflito de banco SIGNIFICA para quem está no balcão.

Toda violação de unicidade virava a mesma frase — "já existe um registro com
estes dados" —, que não diz o que o operador fez, em qual registro, nem o que
fazer a seguir. Ele relê a tela, repete o gesto, e chega o mesmo erro.

Aqui ficam as restrições que ele ENCOSTA na prática. O que não estiver nesta
lista continua caindo na frase geral: é melhor uma frase vaga do que uma
específica e errada.
"""
#: A chave é o nome da restrição (o PostgreSQL a cita na mensagem) ou um
#: pedaço que o SQLite cita.
CONFLITOS_CONHECIDOS = {
    "unique_order_sequence_by_branch": (
        "Este número de pedido já existe. Se isso se repetir, dois servidores "
        "podem estar numerando na mesma faixa — confira `SYNC_NODE_TYPE` (a "
        "loja usa `local`, o servidor central usa `cloud`)."
    ),
    "unique_order_item_per_command_item": (
        "Esta anotação da comanda já está em uma conta. Remova o cartão "
        "daquela conta antes de cobrá-lo aqui."
    ),
    "unique_command_number_by_restaurant": (
        "Já existe uma comanda com este número neste restaurante."
    ),
    "unique_command_code_by_restaurant": (
        "Já existe uma comanda com este código neste restaurante."
    ),
    "unique_table_number_by_branch": (
        "Já existe uma mesa com este número nesta filial."
    ),
    "unique_printer_by_branch": (
        "Já existe uma impressora com este nome nesta filial."
    ),
}
