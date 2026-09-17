"""`manage.py sync_worker` — o processo de sincronização do nó LOCAL.

É este o container `sync_worker` do docker-compose.local. Ele NÃO é um worker
Celery: não consome fila de broker, ele mantém a conexão WSS com a nuvem. O
Celery continua cuidando das tarefas periódicas (retry, reconciliação,
limpeza) em `apps/synchronization/tasks/`.
"""
import asyncio
import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.synchronization.constants import NodeType
from apps.synchronization.services import autostart, guard, nodes
from apps.synchronization.worker import LocalSyncWorker
from apps.synchronization.worker_steps import estado_da_fila

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Mantém a conexão de sincronização da loja com a nuvem."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=2.0,
                            help="segundos entre varreduras da outbox quando ela está vazia")
        parser.add_argument("--heartbeat", type=float, default=20.0,
                            help="segundos entre heartbeats")
        parser.add_argument("--once", action="store_true",
                            help="conecta, esvazia a fila uma vez e sai (útil em teste)")

    def handle(self, *args, **options):
        try:
            guard.ensure_enabled()
        except guard.SyncDisabled as erro:
            raise CommandError(str(erro)) from erro

        if guard.node_type() != NodeType.LOCAL:
            raise CommandError(
                "sync_worker só roda no nó LOCAL. A nuvem recebe conexões pelo "
                "consumer WSS do próprio backend (config/routing.py)."
            )

        config = self._esperar_credencial(options)
        if config is None:
            return
        self.stdout.write(self.style.SUCCESS(
            f"sync: worker local iniciando. Nó {config['node_id']} -> {config['url']}"
        ))
        self._mostrar_fila()

        worker = LocalSyncWorker(
            config=config,
            intervalo=options["interval"],
            heartbeat=options["heartbeat"],
            once=options["once"],
        )
        asyncio.run(self._executar(worker))

    async def _executar(self, worker):
        laco = asyncio.get_running_loop()
        for sinal in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
            if sinal is None:
                continue
            try:
                laco.add_signal_handler(sinal, worker.stop)
            except NotImplementedError:
                # Windows: o Ctrl+C chega como KeyboardInterrupt e basta.
                pass
        try:
            await worker.run()
        except KeyboardInterrupt:  # pragma: no cover
            worker.stop()

    def _esperar_credencial(self, options):
        """Espera até ter identidade e credencial. Não morre por não ter.

        Uma loja é ligada antes de a nuvem estar pronta, antes de alguém ter
        criado a conta, antes de o link subir. Sair com traceback nesse caso
        deixa o container em laço de reinício e enche o log de pilha — quando a
        resposta certa é uma linha dizendo o que falta, e paciência.

        Com `--once` não há espera: quem está testando quer o veredito agora.
        """
        intervalo = max(10.0, float(options.get("heartbeat") or 20.0))
        primeira = True
        while True:
            _matriculou, aviso = autostart.ensure_enrolled(log=self.stdout.write)
            try:
                return self._config()
            except (CommandError, nodes.NodeNotConfigured) as erro:
                motivo = aviso or str(erro)
                if primeira or not options.get("once"):
                    self.stdout.write(self.style.WARNING(f"sync: {motivo}"))
                if options.get("once"):
                    raise CommandError(motivo) from erro
                if primeira:
                    self.stdout.write(
                        "sync: o backend da loja segue operando normalmente; os eventos "
                        f"ficam na outbox. Nova tentativa a cada {intervalo:.0f}s."
                    )
                    primeira = False
                time.sleep(intervalo)
                nodes.invalidate_cache()

    def _config(self):
        proprio = nodes.self_node()
        url = getattr(settings, "SYNC_CLOUD_WSS_URL", "")
        token = getattr(settings, "SYNC_AUTH_TOKEN", "")
        if not url or not token:
            raise CommandError(
                "Faltam SYNC_CLOUD_WSS_URL e/ou SYNC_AUTH_TOKEN. "
                "Rode `manage.py sync_install_node` com o pacote gerado na nuvem."
            )
        return {
            "url": url,
            "token": token,
            "node_id": str(proprio.id),
            "pair_id": str(proprio.pair_id),
            "account_id": str(proprio.account_id),
            "key": getattr(settings, "SYNC_ENCRYPTION_KEY", "") or None,
            "key_id": getattr(settings, "SYNC_ENCRYPTION_KEY_ID", ""),
            "app_version": getattr(settings, "SYNC_APP_VERSION", ""),
        }

    def _mostrar_fila(self):
        """O primeiro log tem de dizer o que ficou para trás desde o último boot."""
        estado = estado_da_fila()
        if not estado.get("configurado"):
            return
        self.stdout.write(
            f"sync: fila ao subir — {estado['pendentes']} a enviar, "
            f"{estado['nao_confirmados']} sem confirmação, "
            f"{estado['a_aplicar']} a aplicar, {estado['mortos']} mortos."
        )
