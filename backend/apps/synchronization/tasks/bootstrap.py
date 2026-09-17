"""A carga completa, fora do processo HTTP (§14.2)."""
import logging

from celery import shared_task

from apps.synchronization.models import SyncRun
from apps.synchronization.services import bootstrap, guard

logger = logging.getLogger(__name__)


@shared_task(name="sync.run_bootstrap", queue="sync.bootstrap", time_limit=3 * 60 * 60)
def run_bootstrap(run_id):
    """Gera o manifesto e os eventos da carga. Retomável por construção.

    O que ela produz são eventos comuns na outbox — o envio em si continua
    sendo do worker da conexão. Matar esta tarefa no meio não desfaz nada do
    que já foi gerado.
    """
    if not guard.is_enabled():
        return {"erro": "sincronização desligada"}

    run = SyncRun.objects.filter(pk=run_id).first()
    if run is None:
        logger.error("sync: carga %s não existe", run_id)
        return {"erro": "carga inexistente"}

    try:
        manifesto = bootstrap.build_manifest(run)
        bootstrap.generate_events(run)
        bootstrap.finish(run)
        logger.info("sync: carga %s concluída (%s entidades)", run.id, len(manifesto))
        return {"run_id": str(run.id), "entidades": len(manifesto), "registros": run.total_records}
    except Exception as erro:  # noqa: BLE001 — a falha tem de ficar no SyncRun
        logger.exception("sync: carga %s falhou", run.id)
        bootstrap.finish(run, error=str(erro))
        return {"erro": str(erro)}
