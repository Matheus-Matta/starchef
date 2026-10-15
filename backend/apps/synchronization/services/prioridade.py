"""A comanda fura a fila: ela é o que o salão e o caixa leem AGORA.

O garçom lança no celular e o caixa lê o cartão segundos depois — muitas vezes
em servidores diferentes (o celular caiu na nuvem, o caixa está na loja). Duas
esperas separavam um do outro, e as duas somem aqui:

* **O aviso.** A nuvem só avisava a loja no aviso periódico (10 s). Agora,
  quando uma transação grava evento da comanda, o aviso sai no COMMIT
  (`avisar_no_commit`). `on_commit` aqui é certo — e a outbox proíbe para o
  EVENTO, não para o aviso: o evento já está gravado; perder o aviso custa só
  esperar o periódico, que continua de pé.
* **A fila.** Depois de uma queda, a anotação ficava atrás de centenas de
  eventos de cadastro e estoque. Agora ela sai no primeiro lote
  (`primeiro_o_urgente`). Furar a ordem é seguro porque o destino já sabe
  esperar: um evento cujo pai ainda não chegou fica guardado e é aplicado na
  hora em que o pai chega (`retry.acordar_quem_espera_dependencia`). E os
  eventos da MESMA entidade continuam na ordem deles, porque são todos
  urgentes ou nenhum.

Prioridade para tudo é prioridade para nada: só a comanda entra.
"""
import logging

from django.db import connection, transaction

logger = logging.getLogger(__name__)

URGENTES = frozenset({
    "command",
    "command_batch",
    "command_item",
    "command_item_addon",
    "command_log",
})


def primeiro_o_urgente(consulta, limite):
    """Até `limite` eventos da consulta, os urgentes na frente."""
    urgentes = list(consulta.filter(entity_type__in=URGENTES)[:limite])
    if not urgentes:
        return list(consulta[:limite])
    resto = consulta.exclude(pk__in=[evento.pk for evento in urgentes])
    return urgentes + list(resto[: max(limite - len(urgentes), 0)])


def avisar_no_commit(entity_type, destino):
    """Na nuvem, avisa a loja de destino assim que a transação confirmar.

    Uma vez por destino e por transação: uma venda que grava trinta anotações
    manda um aviso, não trinta.
    """
    from apps.synchronization.services import nodes

    if entity_type not in URGENTES or destino is None or not nodes.is_cloud():
        return
    grupo = destino.group_name
    # A própria fila de callbacks da transação é o registro de "já vai avisar":
    # desfeita a transação, ela some junto, e nada fica marcado à toa.
    if any(getattr(funcao, "_sync_grupo", None) == grupo for _, funcao, *_ in connection.run_on_commit):
        return

    def _enviar():
        try:
            _avisar(grupo)
        except Exception:  # noqa: BLE001 — o aviso periódico cobre a falha
            logger.warning("sync: aviso imediato para %s falhou; fica para o periódico.", grupo,
                           exc_info=True)

    _enviar._sync_grupo = grupo
    transaction.on_commit(_enviar)


def _avisar(grupo):
    from channels.layers import get_channel_layer

    from apps.synchronization.tasks.dispatch import _avisar as avisar_grupo

    camada = get_channel_layer()
    if camada is None:
        return False
    return avisar_grupo(camada, grupo)
