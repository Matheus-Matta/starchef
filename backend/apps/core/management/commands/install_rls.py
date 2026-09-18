"""`manage.py install_rls` — o isolamento de conta imposto pelo PostgreSQL.

Rode no deploy da NUVEM, depois do `migrate`. É idempotente: recria as
políticas todas as vezes, então acompanha tabela nova sem precisar de migration
— e sem uma migration que envelhece junto com o modelo de dados.

Instalar a política NÃO liga a proteção sozinho. Falta `RLS_ENABLED=true`, que
é o que faz a aplicação dizer ao banco em nome de quem está falando. A ordem
importa e é esta:

    1. manage.py install_rls --status     (veja o que falta)
    2. manage.py install_rls              (cria as políticas)
    3. RLS_ENABLED=true                   (a aplicação passa a se identificar)

Invertida, o passo 2 sem o 3 faz toda consulta devolver zero linha.
"""
from django.core.management.base import BaseCommand

from apps.core import rls


class Command(BaseCommand):
    help = "Instala as políticas de Row Level Security por conta."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true", help="remove em vez de instalar")
        parser.add_argument("--status", action="store_true", help="só mostra o que existe hoje")

    def handle(self, *args, **options):
        if not rls.is_postgres():
            self.stdout.write(self.style.WARNING(
                "Banco não é PostgreSQL: RLS não existe aqui. O isolamento "
                "continua sendo só o do ORM (TenantQuerySetMixin)."
            ))
            return

        if options["status"]:
            return self._status()

        if options["remove"]:
            total = rls.uninstall(log=self.stdout.write)
            self.stdout.write(self.style.SUCCESS(f"{total} tabela(s) liberada(s)."))
            return

        total = rls.install(log=self.stdout.write)
        self.stdout.write(self.style.SUCCESS(f"{total} tabela(s) protegida(s)."))
        if not rls.esta_ligada():
            self.stdout.write(self.style.WARNING(
                "RLS_ENABLED continua false: as políticas existem, mas a aplicação "
                "ainda não diz ao banco em nome de quem fala — e sem isso a "
                "política não deixaria passar nada. Ligue a variável no mesmo "
                "deploy em que rodar este comando."
            ))

    def _status(self):
        protegidas = rls.installed()
        faltando = rls.faltando()
        ligada = rls.esta_ligada()

        burla = rls.papel_burla_rls()
        if burla:
            self.stdout.write(self.style.ERROR(
                f"O usuário '{burla[0]}' {burla[1]}. "
                "As políticas abaixo NÃO valem para esta conexão, por mais "
                "verde que a lista pareça. Crie um usuário de aplicação sem "
                "SUPERUSER e sem BYPASSRLS antes de confiar neste relatório."
            ))

        self.stdout.write(f"Política: {rls.POLITICA}")
        self.stdout.write(f"RLS_ENABLED: {'sim' if ligada else 'não'}")
        self.stdout.write(f"Tabelas de conta: {len(rls.tabelas_multitenant())}")
        self.stdout.write(f"Com política: {len(protegidas)}")

        if faltando:
            self.stdout.write(self.style.ERROR(f"Sem política: {len(faltando)}"))
            for tabela in faltando:
                self.stdout.write(f"  {tabela}")
        else:
            self.stdout.write(self.style.SUCCESS("Nenhuma tabela de conta sem política."))
