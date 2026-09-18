"""Prazo de validade para fila endereçada a nó que não responde.

O defeito que isto fecha: a nuvem gerava a carga inicial para o nó de uma
loja, a loja rematriculava e passava a conectar por OUTRO nó, e as centenas de
eventos da carga antiga ficavam ali — endereçados a uma ficha que ninguém mais
usa. Sem erro, sem tentativa, sem prazo. Para sempre.

A rede de segurança que deveria pegar isso não pegava, por duas razões numa
linha só (`tasks/reconcile.py`):

    SyncNode.objects.filter(status=ACTIVE, last_seen_at__lt=corte)

`status=ACTIVE` não inclui o nó que ficou em PENDING por nunca ter conectado;
e `last_seen_at__lt` nunca casa com `NULL`, que é exatamente o valor de quem
nunca conectou. O nó problemático era justamente o invisível.

Descartar a fila de SAÍDA não perde nada: ela é regenerável a partir do estado
atual do banco, e uma carga nova produz dados mais recentes que os guardados.
A fila de ENTRADA é outra história — é venda, pagamento, sangria que a loja
mandou e este lado ainda não aplicou — e nada aqui encosta nela.
"""
import logging

from django.conf import settings
from django.utils import timezone

from apps.synchronization.constants import NodeStatus, NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import recovery

logger = logging.getLogger(__name__)

#: Dias sem NUNCA ter conectado até a fila daquele nó expirar.
DIAS_NUNCA_VISTO_PADRAO = 7
#: Dias de silêncio, para um nó que já conectou algum dia.
DIAS_CALADO_PADRAO = 30


def prazos():
    return (
        int(getattr(settings, "SYNC_STALE_NEVER_SEEN_DAYS", DIAS_NUNCA_VISTO_PADRAO)),
        int(getattr(settings, "SYNC_STALE_SILENT_DAYS", DIAS_CALADO_PADRAO)),
    )


def nos_vencidos(agora=None):
    """Os nós cuja fila de saída já passou do prazo.

    Devolve `[(no, motivo)]`. Um nó revogado entra na lista sem esperar prazo:
    revogar é dizer que aquele vínculo acabou.
    """
    agora = agora or timezone.now()
    dias_nunca, dias_calado = prazos()

    nunca = agora - timezone.timedelta(days=dias_nunca)
    calados = agora - timezone.timedelta(days=dias_calado)

    vencidos = []
    # `is_self=False`: a própria instalação não tem fila endereçada a si.
    for no in SyncNode.objects.filter(is_self=False, node_type=NodeType.LOCAL):
        if no.status == NodeStatus.REVOKED:
            vencidos.append((no, "vínculo revogado"))
        elif no.last_seen_at is None:
            # O caso que a reconciliação não enxergava: `NULL` nunca casa com
            # uma comparação de data.
            if no.created_at < nunca:
                vencidos.append((no, f"nunca conectou em {dias_nunca} dia(s)"))
        elif no.last_seen_at < calados:
            vencidos.append((no, f"calado há mais de {dias_calado} dia(s)"))
    return vencidos


def expirar_filas(agora=None, dry_run=False):
    """Descarta a fila de saída dos nós vencidos. Devolve o que foi feito."""
    resultado = {"nos": 0, "eventos": 0, "cargas": 0, "detalhe": []}

    for no, motivo in nos_vencidos(agora=agora):
        pendentes = recovery.snapshot(node=no)["nao_enviados"]
        if not pendentes:
            continue

        resultado["nos"] += 1
        resultado["detalhe"].append({"node": str(no.id), "nome": no.name,
                                     "motivo": motivo, "eventos": pendentes})
        if dry_run:
            resultado["eventos"] += pendentes
            continue

        eventos, cargas = recovery.discard_outbound(no)
        resultado["eventos"] += eventos
        resultado["cargas"] += cargas
        logger.warning(
            "sync: fila de %s expirada (%s) — %s evento(s) descartado(s). "
            "Uma carga nova reconstrói tudo a partir do estado atual.",
            no.name, motivo, eventos,
        )

    return resultado


def superar_nos_irmaos(novo_no, *, motivo=""):
    """Na rematrícula, a ficha antiga da MESMA loja para de valer.

    Sem isto, a loja que rematricula deixa para trás um nó com a carga inteira
    endereçada a ele — e passa a conectar pelo nó novo, que não tem nada. A
    nuvem responde "0 pendentes" e nada acontece, sem erro em lugar nenhum.

    O casamento é por `(conta, restaurante)` quando há restaurante, e por
    `(conta, nome)` quando não há. Nunca atravessa conta: seria misturar dados
    de dois clientes.
    """
    irmaos = SyncNode.objects.filter(
        account_id=novo_no.account_id, node_type=NodeType.LOCAL, is_self=False
    ).exclude(pk=novo_no.pk)

    if novo_no.restaurant_id:
        irmaos = irmaos.filter(restaurant_id=novo_no.restaurant_id)
    else:
        irmaos = irmaos.filter(restaurant__isnull=True, name=novo_no.name)

    total_eventos = 0
    superados = 0
    for irmao in irmaos:
        eventos, _cargas = recovery.discard_outbound(irmao)
        total_eventos += eventos
        superados += 1
        SyncNode.objects.filter(pk=irmao.pk).update(
            status=NodeStatus.REVOKED,
            is_active=False,
            last_error=motivo or f"Superado pela matrícula de {novo_no.id}.",
        )
        logger.warning(
            "sync: nó %s superado pela rematrícula de %s — %s evento(s) "
            "da fila antiga descartados.", irmao.id, novo_no.id, eventos,
        )

    return superados, total_eventos
