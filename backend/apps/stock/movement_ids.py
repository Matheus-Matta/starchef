"""O id do movimento de estoque, CALCULADO da `source_key` quando ela existe.

A mesma venda que chega aos dois servidores (a loja gravou e caiu antes de
responder; o terminal reenviou à nuvem) faz a MESMA baixa nos dois, com a
mesma `source_key`. Com id sorteado, a sincronização batia na trava única da
`source_key` e virava conflito; calculado dela, é o mesmo movimento nos dois.
"""
import uuid

_ESPACO = uuid.UUID("4d2a9c71-5e3b-4f08-a6d2-9b7e1c5f3a28")


def id_do_movimento(account_id, source_key):
    return uuid.uuid5(_ESPACO, f"{account_id}:{source_key}")
