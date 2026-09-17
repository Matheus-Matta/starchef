"""As métricas do §19.1, no formato de texto do Prometheus.

Por que não usar `prometheus_client`: ele mantém os contadores em memória do
processo, e aqui rodam vários — gunicorn com N workers, o celery, o
sync_worker. Cada um responderia um número diferente para a mesma pergunta.

Os números desta sincronização já vivem no PostgreSQL, que é a fonte da
verdade para todo o resto: é de lá que eles saem, e por isso qualquer processo
responde o mesmo valor. O custo é uma consulta por raspagem, aceitável para
algo raspado a cada 15-60 segundos.
"""
from django.db.models import Count, Max, Min
from django.utils import timezone

from apps.synchronization.constants import (
    ConflictStatus,
    Direction,
    EventStatus,
    NodeStatus,
    RunStatus,
)

PREFIXO = "sync"


def _linha(nome, valor, rotulos=None):
    if not rotulos:
        return f"{PREFIXO}_{nome} {valor}"
    pares = ",".join(f'{k}="{_escapar(str(v))}"' for k, v in sorted(rotulos.items()))
    return f"{PREFIXO}_{nome}{{{pares}}} {valor}"


def _escapar(valor):
    return valor.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _bloco(nome, ajuda, tipo, amostras):
    """Um HELP/TYPE e suas amostras. Sem amostra, o bloco inteiro some."""
    if not amostras:
        return []
    return [f"# HELP {PREFIXO}_{nome} {ajuda}", f"# TYPE {PREFIXO}_{nome} {tipo}", *amostras]


def coletar():
    """Todas as métricas, como lista de linhas."""
    from apps.synchronization.models import SyncConflict, SyncEvent, SyncNode, SyncRun

    linhas = []
    linhas += _conexoes(SyncNode)
    linhas += _eventos(SyncEvent)
    linhas += _atraso(SyncEvent)
    linhas += _conflitos(SyncConflict)
    linhas += _cargas(SyncRun)
    linhas += _ultimo_sucesso(SyncNode)
    return linhas


def _conexoes(SyncNode):
    por_estado = dict(
        SyncNode.objects.values_list("status").annotate(total=Count("id"))
    )
    ativos = por_estado.get(NodeStatus.ACTIVE, 0)
    amostras = [_linha("connections_active", ativos)]
    amostras += [
        _linha("nodes", total, {"status": estado})
        for estado, total in sorted(por_estado.items())
    ]
    return _bloco("connections_active", "Nós com conexão ativa agora.", "gauge",
                  [amostras[0]]) + _bloco(
        "nodes", "Nós cadastrados, por estado.", "gauge", amostras[1:])


def _eventos(SyncEvent):
    """Pendentes, falhos e mortos — os três que disparam alerta (§19.3)."""
    contagem = {
        estado: total
        for estado, total in SyncEvent.objects.values_list("status").annotate(
            total=Count("id")
        )
    }
    pendentes = sum(contagem.get(e, 0) for e in EventStatus.OUTBOUND_OPEN)
    falhos = contagem.get(EventStatus.FAILED, 0)
    mortos = contagem.get(EventStatus.DEAD, 0)

    linhas = _bloco("events_pending", "Eventos que ainda precisam sair.", "gauge",
                    [_linha("events_pending", pendentes)])
    linhas += _bloco("events_failed", "Eventos em retentativa.", "gauge",
                     [_linha("events_failed", falhos)])
    linhas += _bloco("events_dead", "Eventos que desistiram e exigem ação manual.",
                     "gauge", [_linha("events_dead", mortos)])
    linhas += _bloco(
        "events", "Eventos por estado e direção.", "gauge",
        [_linha("events", total, {"status": estado}) for estado, total in sorted(contagem.items())],
    )
    return linhas


def _atraso(SyncEvent):
    """Idade do evento pendente mais antigo. É o que denuncia fila parada.

    Um contador de pendentes alto pode ser só um pico; um evento de duas horas
    parado é sempre problema.
    """
    mais_antigo = (
        SyncEvent.objects.filter(
            direction=Direction.OUTBOUND, status__in=list(EventStatus.OUTBOUND_OPEN)
        )
        .aggregate(inicio=Min("created_at"))["inicio"]
    )
    atraso = (timezone.now() - mais_antigo).total_seconds() if mais_antigo else 0
    return _bloco(
        "event_lag_seconds", "Idade, em segundos, do evento pendente mais antigo.",
        "gauge", [_linha("event_lag_seconds", round(atraso, 1))],
    )


def _conflitos(SyncConflict):
    abertos = SyncConflict.objects.filter(status=ConflictStatus.OPEN).count()
    return _bloco("conflicts_open", "Conflitos aguardando decisão.", "gauge",
                  [_linha("conflicts_open", abertos)])


def _cargas(SyncRun):
    em_andamento = SyncRun.objects.filter(status__in=list(RunStatus.BUSY))
    amostras = [
        _linha("bootstrap_progress", run.progress_percent,
               {"run": str(run.id), "type": run.run_type, "node": str(run.target_node_id)})
        for run in em_andamento[:20]
    ]
    return _bloco("bootstrap_progress", "Progresso (%) das cargas em andamento.",
                  "gauge", amostras)


def _ultimo_sucesso(SyncNode):
    """Timestamp Unix da última sincronização de cada nó.

    Em gauge e não em "segundos atrás" de propósito: o Prometheus calcula a
    idade sozinho com `time() - metric`, e um timestamp absoluto continua certo
    mesmo se a raspagem atrasar.
    """
    amostras = []
    for no in SyncNode.objects.exclude(last_sync_at__isnull=True)[:100]:
        amostras.append(_linha(
            "last_success_timestamp", int(no.last_sync_at.timestamp()),
            {"node": str(no.id), "type": no.node_type, "account": str(no.account_id)},
        ))
    return _bloco("last_success_timestamp",
                  "Unix timestamp da última sincronização bem-sucedida do nó.",
                  "gauge", amostras)


def render():
    """O corpo da resposta, pronto para o coletor."""
    return "\n".join(coletar()) + "\n"


def resumo():
    """Os mesmos números em dicionário — para log, Admin e healthcheck."""
    from apps.synchronization.models import SyncConflict, SyncEvent, SyncNode

    agregado = SyncEvent.objects.aggregate(
        total=Count("id"), mais_recente=Max("created_at")
    )
    return {
        "nodes_active": SyncNode.objects.filter(status=NodeStatus.ACTIVE).count(),
        "events_total": agregado["total"],
        "events_dead": SyncEvent.objects.filter(status=EventStatus.DEAD).count(),
        "conflicts_open": SyncConflict.objects.filter(status=ConflictStatus.OPEN).count(),
        "last_event_at": agregado["mais_recente"],
    }
