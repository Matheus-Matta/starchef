"""`manage.py sync_merge_nodes` — dois nós que são a mesma loja viram um.

Para que serve: uma loja que rematriculou antes da correção que faz o backend
local reler as credenciais gravadas ganhou um SEGUNDO nó na nuvem. A carga
inicial foi gerada para o primeiro e a loja passou a conectar pelo segundo —
então o despacho, que filtra pelo destino, devolve lote vazio. Centenas de
eventos ficam em PENDING com `tentativas=0`, sem erro em lugar nenhum.

    manage.py sync_merge_nodes --list              # o que parece duplicado
    manage.py sync_merge_nodes --from A --to B --dry-run
    manage.py sync_merge_nodes --from A --to B

Quem decide que os dois nós são a mesma loja é você. Duas lojas podem ter o
mesmo nome, e casar por nome automaticamente seria pior que o problema — por
isso `--list` sugere e só o `--from/--to` executa.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import merge_nodes


class Command(BaseCommand):
    help = "Funde dois nós de sincronização que representam a mesma instalação."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true",
                            help="mostra os nós que parecem duplicados e sai")
        parser.add_argument("--from", dest="origem",
                            help="id do nó a ser absorvido (será APAGADO)")
        parser.add_argument("--to", dest="destino",
                            help="id do nó que permanece")
        parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                            help="mostra o que mudaria, sem gravar nada")

    def handle(self, *args, **options):
        if options["list"]:
            self._listar()
            return

        if not options["origem"] or not options["destino"]:
            raise CommandError(
                "Informe --from e --to (use --list para ver os candidatos)."
            )

        origem = self._no(options["origem"], "--from")
        destino = self._no(options["destino"], "--to")

        self._descrever(origem, "origem (será apagado)")
        self._descrever(destino, "destino (permanece)")

        try:
            resumo = merge_nodes.merge(origem, destino, dry_run=options["dry_run"])
        except merge_nodes.MergeRecusada as erro:
            raise CommandError(str(erro)) from erro

        rotulo = "SERIAM movidos" if options["dry_run"] else "movidos"
        self.stdout.write("")
        self.stdout.write(f"  eventos originados aqui {rotulo} : "
                          f"{resumo['eventos_como_origem']} (renumerados)")
        self.stdout.write(f"  eventos destinados aqui {rotulo} : "
                          f"{resumo['eventos_como_destino']}")
        self.stdout.write(f"  cargas (runs) .................... : {resumo['runs']}")
        self.stdout.write(f"  conflitos ....................... : {resumo['conflitos']}")
        self.stdout.write(f"  transferências .................. : {resumo['transferencias']}")
        if resumo["transferencias_descartadas"]:
            self.stdout.write(
                f"  transferências descartadas ...... : "
                f"{resumo['transferencias_descartadas']} (duplicadas, serão refeitas)"
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(
                "\nNada foi gravado. Rode sem --dry-run para aplicar."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nFusão concluída. A loja recebe a fila na próxima conexão."
            ))

    # ── auxiliares ──────────────────────────────────────────────────────────
    def _listar(self):
        grupos = merge_nodes.candidatos()
        if not grupos:
            self.stdout.write("Nenhum nó duplicado encontrado.")
            return

        self.stdout.write("Nós que parecem ser a mesma instalação:\n")
        for (_conta, _restaurante, nome), nos in grupos.items():
            self.stdout.write(f"  {nome}")
            for no in nos:
                self._descrever(no, indent="    ")
            self.stdout.write("")
        self.stdout.write(
            "Confira ANTES de fundir. O candidato a --to costuma ser o que tem\n"
            "`visto` recente: é o nó pelo qual a loja conecta hoje."
        )

    def _descrever(self, no, titulo=None, indent="  "):
        if titulo:
            self.stdout.write(f"\n{titulo}:")
        pendentes = SyncEvent.objects.filter(target_node=no).count()
        originados = SyncEvent.objects.filter(source_node=no).count()
        visto = no.last_seen_at or "nunca"
        self.stdout.write(
            f"{indent}{no.id}  {no.node_type}  {no.status:<8} visto={visto}  "
            f"destino_de={pendentes} origem_de={originados}"
        )

    def _no(self, identificador, rotulo):
        no = SyncNode.objects.filter(pk=identificador).first()
        if no is None:
            raise CommandError(f"{rotulo}: nó {identificador} não existe.")
        return no
