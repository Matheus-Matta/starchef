"""`manage.py sync_status` — o que está na fila, parado ou morto.

O primeiro comando a rodar quando alguém pergunta "a loja está sincronizando?".
Só lê; não muda nada.
"""
from django.core.management.base import BaseCommand

from apps.synchronization.constants import NodeStatus
from apps.synchronization.models import SyncNode
from apps.synchronization.services import guard, recovery, workers


class Command(BaseCommand):
    help = "Mostra o estado da sincronização: nós, fila, parados e mortos."

    def add_arguments(self, parser):
        parser.add_argument("--account", help="limita a uma conta")
        parser.add_argument("--stuck-minutes", type=int, default=30, dest="stuck_minutes")
        parser.add_argument("--quiet", action="store_true",
                            help="sem relatório: só sai 0 se a fila é legível (healthcheck)")

    def handle(self, *args, **options):
        if options["quiet"]:
            # Modo healthcheck do container: o veredito é conseguir consultar
            # a fila. Nuvem inalcançável NÃO é falha — a loja offline é um
            # estado normal, e um healthcheck que reprovasse isso reiniciaria
            # o worker em looping justamente quando a internet caiu.
            recovery.snapshot()
            return

        self.stdout.write(self.style.MIGRATE_HEADING("Configuração"))
        self.stdout.write(f"  SYNC_ENABLED ......: {guard.is_enabled()}")
        self.stdout.write(f"  SYNC_ENVIRONMENT ..: {guard.current_environment() or '(vazio)'}")
        self.stdout.write(f"  SYNC_NODE_TYPE ....: {guard.node_type() or '(vazio)'}")

        self._workers()
        self._nos(options.get("account"))
        self._fila(options.get("account"))
        self._parados(options["stuck_minutes"])

    def _workers(self):
        """Alguém está consumindo as filas do sync?

        Sem isto a falha é muda: as tarefas são enfileiradas, ninguém as tira,
        e o sintoma que chega é "a loja conectou mas não recebeu nada".
        """
        if not guard.is_enabled():
            return
        self.stdout.write(self.style.MIGRATE_HEADING("\nWorkers Celery"))
        aviso = workers.diagnostico()
        if aviso is None:
            self.stdout.write(self.style.SUCCESS("  todas as filas do sync têm worker consumindo"))
        else:
            self.stdout.write(self.style.ERROR(f"  {aviso}"))

    def _nos(self, account_id):
        consulta = SyncNode.objects.all()
        if account_id:
            consulta = consulta.filter(account_id=account_id)
        self.stdout.write(self.style.MIGRATE_HEADING("\nNós"))
        if not consulta.exists():
            self.stdout.write("  (nenhum nó cadastrado)")
            return
        for no in consulta.order_by("node_type", "name"):
            estilo = self.style.SUCCESS if no.status == NodeStatus.ACTIVE else self.style.WARNING
            marca = " [este]" if no.is_self else ""
            self.stdout.write(
                f"  {no.node_type:<6} {no.name[:28]:<28}{marca} "
                + estilo(f"{no.status:<8}")
                + f" visto={no.last_seen_at or '-'} "
                f"env={no.last_sent_cursor} rec={no.last_received_cursor}"
            )

    def _fila(self, account_id):
        retrato = recovery.snapshot(account_id=account_id)
        self.stdout.write(self.style.MIGRATE_HEADING("\nFila"))
        self.stdout.write(f"  total ............: {retrato['total']}")
        self.stdout.write(f"  a enviar .........: {retrato['nao_enviados']}")
        self.stdout.write(f"  a aplicar ........: {retrato['nao_aplicados']}")
        mortos = retrato["mortos"]
        linha = f"  mortos ...........: {mortos}"
        self.stdout.write(self.style.ERROR(linha) if mortos else linha)
        for estado, dados in retrato["por_estado"].items():
            self.stdout.write(
                f"    {estado:<14} {dados['total']:>7}  mais antigo: {dados['mais_antigo']}"
            )

    def _parados(self, minutos):
        parados = recovery.stuck(minutos)
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nParados há mais de {minutos} min"))
        if not parados:
            self.stdout.write(self.style.SUCCESS("  nenhum"))
            return
        for evento in parados[:20]:
            self.stdout.write(self.style.WARNING(
                f"  {evento.created_at:%d/%m %H:%M} {evento.entity_type:<20} "
                f"{evento.status:<12} tentativas={evento.attempts} {evento.last_error[:60]}"
            ))
        if len(parados) > 20:
            self.stdout.write(f"  … e mais {len(parados) - 20}")
