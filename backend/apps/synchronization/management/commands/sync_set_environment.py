"""`manage.py sync_set_environment` — move as fichas dos nós de ambiente.

O ambiente faz parte da identidade do nó: `authentication._validar_ambiente`
recusa o HELLO quando a ficha na nuvem diz um ambiente e o nó declara outro.
Isso é o que impede uma loja de homologação entrar na nuvem de produção — e é
também o que faz a virada de `development` para `production` exigir este
comando.

Trocar só a variável derruba TODAS as lojas de uma vez, cada uma com "ambiente
incompatível", porque as fichas continuam em `development`.

## A virada, na ordem

1. **Nuvem**: `SYNC_ENVIRONMENT=production` no `.env` e reinicie.
2. **Nuvem**: `manage.py sync_set_environment --to production`
3. **Cada loja**: `SYNC_ENVIRONMENT=production` no `.env` e reinicie.

Entre 1 e 3 as lojas são recusadas no HELLO. **Isso não perde nada**: a outbox
é durável, o worker reconecta com backoff, e tudo que foi vendido no intervalo
sai assim que a loja voltar. O que se perde é tempo, e por isso vale fazer os
três passos na mesma janela.

Quem tem poucas lojas pode inverter 2 e 3 sem diferença prática — a janela de
recusa existe de qualquer jeito, só muda de lado.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.synchronization.constants import ENVIRONMENTS_ALLOWED
from apps.synchronization.models import SyncNode


class Command(BaseCommand):
    help = "Move as fichas dos nós de sincronização para outro ambiente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to", required=True,
            help="Ambiente de destino: " + ", ".join(sorted(ENVIRONMENTS_ALLOWED)),
        )
        parser.add_argument(
            "--from", dest="origem", default="",
            help="Move só as fichas que hoje estão neste ambiente (padrão: todas)",
        )
        parser.add_argument(
            "--node", default="",
            help="Move um nó só, pelo UUID — para migrar loja por loja",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Só mostra o que mudaria",
        )

    def handle(self, *args, **options):
        destino = str(options["to"]).strip().lower()
        if destino not in ENVIRONMENTS_ALLOWED:
            raise CommandError(
                f"Ambiente '{destino}' não existe. Use: "
                + ", ".join(sorted(ENVIRONMENTS_ALLOWED))
            )

        consulta = SyncNode.objects.all()
        if options["origem"]:
            consulta = consulta.filter(environment=options["origem"].strip().lower())
        if options["node"]:
            consulta = consulta.filter(pk=options["node"])
            if not consulta.exists():
                raise CommandError(f"Nó {options['node']} não encontrado.")

        pendentes = consulta.exclude(environment=destino)
        total = pendentes.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                f"Nenhuma ficha para mover: todas já estão em '{destino}'."
            ))
            return self._avisar_variavel(destino)

        for no in pendentes.order_by("node_type", "name")[:50]:
            self.stdout.write(f"  {no.node_type:5} {no.name} — {no.environment} → {destino}")
        if total > 50:
            self.stdout.write(f"  … e mais {total - 50}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"\n--dry-run: {total} ficha(s) NÃO foram alteradas."))
            return None

        movidas = pendentes.update(environment=destino)
        self.stdout.write(self.style.SUCCESS(f"\n{movidas} ficha(s) movida(s) para '{destino}'."))
        self._avisar_variavel(destino)
        return None

    def _avisar_variavel(self, destino):
        """A ficha é metade do par. A outra metade é o `.env` de cada ponta."""
        atual = str(getattr(settings, "SYNC_ENVIRONMENT", "") or "").strip().lower()
        if atual == destino:
            self.stdout.write(
                "\nSYNC_ENVIRONMENT desta instalação já é "
                f"'{destino}'. Falta cada LOJA ter a mesma variável e reiniciar — "
                "até lá elas são recusadas no HELLO e acumulam na outbox, sem perder nada."
            )
            return
        self.stdout.write(self.style.ERROR(
            f"\nATENÇÃO: SYNC_ENVIRONMENT desta instalação é '{atual or '(vazio)'}', "
            f"não '{destino}'. As fichas foram movidas, mas esta instalação vai "
            f"recusar TODO HELLO até a variável mudar e o processo reiniciar."
        ))
