"""Tarefas Celery da sincronização.

Elas NÃO são o caminho principal: o caminho principal é o `sync_worker`, que
mantém a conexão. Estas tarefas cuidam do que é periódico — reprocessar o que
falhou, aplicar o que ficou parado, reconciliar cursores e limpar o que já foi
confirmado. Uma tarefa perdida não perde nada: o estado está no PostgreSQL e a
próxima execução recomeça de onde parou.
"""
from .apply import apply_pending_events  # noqa: F401
from .bootstrap import run_bootstrap  # noqa: F401
from .cleanup import prune_acknowledged_events  # noqa: F401
from .dirty import collect_dirty_rows, prune_dirty_rows  # noqa: F401
from .dispatch import notify_pending_to_local_nodes  # noqa: F401
from .reconcile import reconcile_nodes  # noqa: F401
from .retry import retry_failed_events  # noqa: F401
