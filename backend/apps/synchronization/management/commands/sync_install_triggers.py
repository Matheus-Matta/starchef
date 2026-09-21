"""`manage.py sync_install_triggers` — a rede de segurança do §11.2.

Rode no deploy, depois do `migrate`. É idempotente: recria a função e as
triggers todas as vezes, então ela acompanha mudanças do catálogo sem precisar
de migration nova — e sem uma migration que envelhece junto com o catálogo.

Fora do PostgreSQL não faz nada e diz isso. O SQLite do desenvolvimento
continua contando só com os signals.
"""
from django.core.management.base import BaseCommand

from apps.synchronization.services import guard, triggers


class Command(BaseCommand):
    help = "Instala as triggers que capturam escrita feita por fora do ORM."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true", help="remove em vez de instalar")
        parser.add_argument("--status", action="store_true", help="só mostra o que existe hoje")
        parser.add_argument("--force", action="store_true",
                            help="instala mesmo com SYNC_ENABLED=false")

    def handle(self, *args, **options):
        if not triggers.is_postgres():
            self.stdout.write(self.style.WARNING(
                "Banco não é PostgreSQL: as triggers não existem aqui. "
                "A captura continua pelos signals (não cobre bulk/SQL direto)."
            ))
            return None

        if options["status"]:
            return self._status()

        # Com a sincronização DESLIGADA a rede de segurança não protege nada —
        # e custa caro: a trigger grava uma linha em `synchronization_syncdirty`
        # a CADA escrita de toda tabela sincronizada, que ninguém vai consumir.
        # Numa nuvem com sync desligado isso é só uma tabela crescendo sozinha.
        #
        # O comando fica no boot do compose de propósito (é idempotente e
        # acompanha o catálogo); esta guarda é o que o torna seguro de deixar
        # lá em qualquer instalação.
        if not guard.is_enabled() and not options["force"] and not options["remove"]:
            self.stdout.write(self.style.WARNING(
                "SYNC_ENABLED=false: triggers NÃO instaladas. "
                "Elas só fazem sentido com a sincronização ligada — sem ela, "
                "gravariam uma marca por escrita que ninguém consumiria. "
                "Use --force para instalar assim mesmo."
            ))
            return None

        if options["remove"]:
            triggers.uninstall(log=self.stdout.write)
            return None

        triggers.install(log=self.stdout.write)
        self.stdout.write(self.style.SUCCESS("Rede de segurança ativa."))
        return None

    def _status(self):
        existentes = triggers.installed()
        ausentes = triggers.faltando()
        self.stdout.write(f"triggers instaladas: {len(existentes)}")
        if ausentes:
            self.stdout.write(self.style.ERROR(f"tabelas SEM trigger: {', '.join(ausentes)}"))
            self.stdout.write("Rode `manage.py sync_install_triggers` para corrigir.")
        else:
            self.stdout.write(self.style.SUCCESS("nenhuma tabela sincronizada sem trigger"))
