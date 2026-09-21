"""O que pode ENTRAR na inbox — e o que fazer com o que não pode.

Fica separado de `inbox.py` porque são duas perguntas diferentes: aqui se
decide o que é admissível; lá, como se grava. A separação importa porque estas
regras têm um detalhe que custou caro — qual delas derruba o lote inteiro e
qual manda só o evento para a quarentena. Lê-las juntas é o que deixa isso
visível.
"""
import logging

from apps.synchronization.services import crypto

logger = logging.getLogger(__name__)

#: Quantas vezes o lote configurado ainda é aceito na recepção.
FOLGA = 4


class CrossTenantRejected(PermissionError):
    """Evento cuja conta não bate com a conexão autenticada. Derruba o lote."""


class BatchRejected(ValueError):
    """Lote fora dos limites combinados — recusado antes de gravar nada."""


class EventQuarantined(ValueError):
    """Um evento que não entra, sem derrubar os outros do lote.

    A diferença entre isto e [BatchRejected] é o que se faz com o RESTO. Um
    evento estragado é problema dele; o lote que veio junto não tem culpa.
    """


def _limites():
    """Tetos de recepção, derivados dos de envio.

    O remetente já corta em `SYNC_BATCH_MAX_EVENTS` e `SYNC_BATCH_MAX_BYTES`,
    mas isso é disciplina de quem envia, e quem valida entrada não pode contar
    com a boa vontade da origem — mesmo autenticada. A folga generosa existe
    para o limite nunca recusar tráfego legítimo: ele é o teto do absurdo, não
    um segundo corte de lote.
    """
    from django.conf import settings

    eventos = int(getattr(settings, "SYNC_BATCH_MAX_EVENTS", 200)) * FOLGA
    bytes_por_evento = int(getattr(settings, "SYNC_BATCH_MAX_BYTES", 1_048_576))
    return eventos, bytes_por_evento


def _validar_lote(events_payload, connection_node):
    """Recusa o lote inteiro ANTES de gravar, se vier fora do combinado.

    Recusar antes importa: gravar metade e estourar no meio deixaria a inbox
    com um pedaço de um lote que a origem considera não entregue, e ela
    reenviaria o lote todo — a deduplicação resolveria, mas o estado
    intermediário é exatamente o que ninguém quer ter de explicar depois.
    """
    max_eventos, _max_bytes = _limites()
    if len(events_payload) > max_eventos:
        logger.error(
            "sync: lote com %s eventos do nó %s (teto %s)",
            len(events_payload), connection_node.id, max_eventos,
        )
        raise BatchRejected(
            f"Lote com {len(events_payload)} eventos; o teto de recepção é {max_eventos}."
        )


def _validar_tamanho(bruto, connection_node):
    """O teto de bytes é por EVENTO, e a recusa também.

    Era o lote que caía quando um evento passava do teto. Um payload grande é
    problema daquele evento; os outros do lote não têm nada com isso.
    """
    _max_eventos, max_bytes = _limites()
    tamanho = len(crypto.canonical_json(bruto.get("payload") or {}))
    if tamanho > max_bytes:
        logger.error(
            "sync: evento %s do nó %s com %s bytes (teto %s)",
            bruto.get("event_id"), connection_node.id, tamanho, max_bytes,
        )
        raise EventQuarantined(
            f"Evento {bruto.get('event_id')} tem {tamanho} bytes; o teto é {max_bytes}."
        )


def _validar_escopo(bruto, connection_node, destino, account_id):
    """Cross-tenant é rejeitado e auditado — nunca aplicado (§9.2).

    As duas checagens levam o MESMO evento ao mesmo destino — a lixeira —, mas
    por caminhos diferentes de propósito:

    * **conta errada** é postura hostil: o payload afirma pertencer a outro
      inquilino. Derruba o lote e a conexão, como sempre derrubou.
    * **destino errado** é erro de endereçamento DENTRO da conta autenticada —
      tipicamente um evento endereçado a um id de nó que deixou de existir
      (ver `sync_merge_nodes`). Derrubar a conexão por causa disso criava um
      laço: o lote voltava, o mesmo evento derrubava de novo, e nada que vinha
      atrás dele chegava nunca. Agora ele vai para a quarentena sozinho.

    Em nenhum dos dois o evento é gravado, e os dois ficam no log.
    """
    conta_evento = str(bruto.get("account_id") or account_id)
    if conta_evento != str(account_id):
        logger.error(
            "sync: account_id adulterado node=%s conta=%s", connection_node.id, conta_evento
        )
        raise CrossTenantRejected("account_id do evento não é o da conexão autenticada.")

    alvo = str(bruto.get("target_node_id") or "")
    if alvo and alvo != str(destino.id):
        logger.error(
            "sync: target_node adulterado node=%s alvo=%s", connection_node.id, alvo
        )
        raise EventQuarantined("target_node do evento não é este nó.")

