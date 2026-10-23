"""`manage.py sync_midia` — os arquivos de mídia que faltam neste servidor.

Sem opção, só lê: por campo de arquivo, quantos registros e quais arquivos
faltam AQUI. Na nuvem, são as fotos da loja com link quebrado; na loja, as que
foram enviadas pelo painel da nuvem.

`--agora` (só na loja) roda a transferência inteira, sem o limite da rodada
periódica: sobe o que só a loja tem e baixa o que só a nuvem tem. É a correção
das fotos que já estão quebradas — o link conserta sozinho quando o arquivo
chega, porque ele é montado do caminho. `--forcar` refaz até o que já consta
como transferido.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.core.rls import escopo_da_plataforma
from apps.synchronization.services import midia, nodes


class Command(BaseCommand):
    help = "Mostra os arquivos de mídia que faltam aqui; --agora transfere (rode na LOJA)."

    def add_arguments(self, parser):
        parser.add_argument("--agora", action="store_true", help="transfere tudo agora (loja)")
        parser.add_argument("--forcar", action="store_true", help="refaz até o que já foi transferido")

    def handle(self, *args, **options):
        with escopo_da_plataforma("sync_midia manual"):
            if options["agora"]:
                self._transferir(options["forcar"])
            else:
                self._relatorio()

    def _transferir(self, forcar):
        if not nodes.is_local():
            raise CommandError("Rode --agora no servidor da LOJA: é ela quem fala com a nuvem.")
        from apps.synchronization.services import midia_envio

        conta = midia_envio.rodada(limite=None, forcar=forcar)
        self.stdout.write(self.style.SUCCESS(
            f"enviados={conta['enviados']} baixados={conta['baixados']} "
            f"falhas={conta['falhas']} já em dia={conta['ja_em_dia']}"
        ))
        if conta["falhas"]:
            self.stdout.write("As falhas tentam de novo sozinhas em 30 min; o motivo está no log (sync-midia).")

    def _relatorio(self):
        for linha in midia.situacao():
            faltando = linha["faltando"]
            self.stdout.write(f"{linha['entidade']}.{linha['campo']}: {linha['total']} com arquivo, "
                              f"{len(faltando)} faltando aqui")
            for caminho in faltando[:20]:
                self.stdout.write(f"    {caminho}")
            if len(faltando) > 20:
                self.stdout.write(f"    ... e mais {len(faltando) - 20}")
