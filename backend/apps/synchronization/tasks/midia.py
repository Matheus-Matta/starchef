"""A rodada periódica dos arquivos de mídia — só na LOJA.

A loja é quem fala com a nuvem (a nuvem não alcança a loja atrás do roteador),
então é ela que sobe a foto que só ela tem e baixa a que só a nuvem tem. Na
nuvem esta tarefa não faz nada. Ver `services/midia.py`.
"""
import logging

from celery import shared_task

from apps.core.rls import trabalho_de_plataforma
from apps.synchronization.services import guard, nodes

logger = logging.getLogger(__name__)


@shared_task(name="sync.sincronizar_midia", queue="sync.reconcile")
@trabalho_de_plataforma("arquivos de midia entre loja e nuvem")
def sincronizar_midia(limite=50):
    if not guard.is_enabled() or not nodes.is_local():
        return {}
    from apps.synchronization.services import midia_envio

    conta = midia_envio.rodada(limite=limite)
    if conta["enviados"] or conta["baixados"] or conta["falhas"]:
        logger.info("sync-midia: %s", conta)
    return conta
