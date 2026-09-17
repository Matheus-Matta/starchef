"""`manage.py sync_provision_node` — cadastra a loja na NUVEM e imprime o pacote.

O token e a chave aparecem UMA vez, aqui. Depois disso o banco só tem o hash e
a impressão digital: não existe comando para "ver de novo" — existe rotacionar.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Account
from apps.restaurants.models import Restaurant
from apps.synchronization.constants import NodeType
from apps.synchronization.services import guard, provisioning


class Command(BaseCommand):
    help = "Cadastra um nó LOCAL na nuvem e gera as credenciais de DEVELOPMENT."

    def add_arguments(self, parser):
        parser.add_argument("--account", required=True, help="ID ou nome da conta")
        parser.add_argument("--restaurant", help="ID do restaurante (opcional)")
        parser.add_argument("--name", required=True, help="nome amigável do servidor da loja")
        parser.add_argument("--cloud-url", required=True, dest="cloud_url",
                            help="ex.: wss://dev-sync.exemplo.com/ws/sync/v1/")
        parser.add_argument("--allowed-ip", dest="allowed_ip")
        parser.add_argument("--env-file", dest="env_file", help="grava o pacote neste arquivo")

    def handle(self, *args, **options):
        try:
            guard.ensure_environment()
        except guard.SyncDisabled as erro:
            raise CommandError(str(erro)) from erro

        if guard.node_type() != NodeType.CLOUD:
            raise CommandError("Este comando roda no nó CLOUD (SYNC_NODE_TYPE=cloud).")

        conta = self._conta(options["account"])
        restaurante = None
        if options.get("restaurant"):
            restaurante = Restaurant.all_objects.filter(pk=options["restaurant"]).first()
            if restaurante is None:
                raise CommandError(f"Restaurante {options['restaurant']} não encontrado.")

        no, pacote = provisioning.provision_local_node(
            account=conta,
            restaurant=restaurante,
            name=options["name"],
            endpoint=options["cloud_url"],
            cloud_endpoint=options["cloud_url"],
            allowed_ip=options.get("allowed_ip"),
        )

        texto = provisioning.env_file_text(pacote)
        if options.get("env_file"):
            with open(options["env_file"], "w", encoding="utf-8") as arquivo:
                arquivo.write(texto + "\n")
            self.stdout.write(self.style.SUCCESS(f"Pacote gravado em {options['env_file']}"))

        self.stdout.write(self.style.SUCCESS(f"\nNó {no.id} cadastrado (pair {no.pair_id}).\n"))
        self.stdout.write(texto)
        self.stdout.write(self.style.WARNING(
            "\nO token e a chave acima NÃO poderão ser recuperados. Guarde agora."
        ))

    def _conta(self, referencia):
        conta = Account.objects.filter(pk=referencia).first() if _parece_uuid(referencia) else None
        conta = conta or Account.objects.filter(name__iexact=referencia).first()
        if conta is None:
            raise CommandError(f"Conta não encontrada: {referencia}")
        return conta


def _parece_uuid(valor):
    return len(str(valor)) >= 32 and "-" in str(valor)
