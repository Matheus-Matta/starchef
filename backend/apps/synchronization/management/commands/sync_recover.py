"""`manage.py sync_recover` — traz de volta o que não foi enviado.

Três usos, do mais comum ao mais grave:

    manage.py sync_recover --requeue                  # mortos voltam para a fila
    manage.py sync_recover --requeue --include-failed # e os que estão falhando
    manage.py sync_recover --export fila.json         # resgate manual em JSON

Nada aqui apaga evento. `--prune` existe e só toca no que o outro lado já
confirmou.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.synchronization.constants import EventStatus
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import recovery


class Command(BaseCommand):
    help = "Reprocessa, exporta ou limpa a fila de sincronização."

    def add_arguments(self, parser):
        parser.add_argument("--requeue", action="store_true", help="devolve eventos à fila")
        parser.add_argument("--include-failed", action="store_true", dest="include_failed",
                            help="com --requeue, inclui os FAILED além dos DEAD")
        parser.add_argument("--export", help="arquivo JSON de destino")
        parser.add_argument("--account", help="limita a uma conta")
        parser.add_argument("--entity", help="limita a um entity_type")
        parser.add_argument("--event-id", dest="event_id", help="um evento específico")
        parser.add_argument("--prune-days", type=int, dest="prune_days",
                            help="apaga confirmados com mais de N dias")

    def handle(self, *args, **options):
        if not any([options["requeue"], options["export"], options["prune_days"]]):
            raise CommandError("Escolha uma ação: --requeue, --export ou --prune-days.")

        if options["requeue"]:
            self._requeue(options)
        if options["export"]:
            self._export(options)
        if options["prune_days"]:
            apagados = recovery.prune(options["prune_days"])
            self.stdout.write(self.style.SUCCESS(
                f"{apagados} evento(s) já confirmados apagados (retenção de "
                f"{options['prune_days']} dias)."
            ))

    def _requeue(self, options):
        eventos = None
        if options.get("event_id"):
            eventos = list(SyncEvent.objects.filter(event_id=options["event_id"]))
            if not eventos:
                raise CommandError(f"Evento {options['event_id']} não encontrado.")

        total = recovery.requeue(
            eventos,
            account_id=options.get("account"),
            entity_type=options.get("entity"),
            apenas_mortos=not options["include_failed"],
        )
        self.stdout.write(self.style.SUCCESS(f"{total} evento(s) devolvidos à fila."))
        if total:
            self.stdout.write("O worker os envia na próxima varredura; o event_id impede duplicação.")

    def _export(self, options):
        consulta = SyncEvent.objects.exclude(status=EventStatus.ACKNOWLEDGED)
        if options.get("account"):
            consulta = consulta.filter(account_id=options["account"])
        if options.get("entity"):
            consulta = consulta.filter(entity_type=options["entity"])
        if options.get("event_id"):
            consulta = consulta.filter(event_id=options["event_id"])

        total = recovery.export(consulta.order_by("created_at"), options["export"])
        self.stdout.write(self.style.SUCCESS(
            f"{total} evento(s) exportados para {options['export']}."
        ))
