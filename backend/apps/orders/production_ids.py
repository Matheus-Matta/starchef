"""O id do lote de produção, CALCULADO do serial que o PDV mandou.

A mesma venda chega aos dois servidores quando a loja grava e cai antes de
responder: o terminal reenvia à nuvem. Com id sorteado, cada servidor criava o
seu lote com o MESMO serial, e a sincronização batia na trava única do serial —
o lote nunca entrava, e os itens que apontam para ele ficavam retentando para
sempre. Calculado do serial, é o mesmo lote nos dois, e a sincronização junta.
Sem serial (envio sem identidade do terminal), o id continua sorteado.
"""
import uuid

_ESPACO = uuid.UUID("0b8f4c2e-7a1d-4e93-b6c5-2f9d8e1a3c47")


def id_do_lote(serial):
    return uuid.uuid5(_ESPACO, f"lote:{serial}")
