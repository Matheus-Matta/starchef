"""`manage.py sync_enroll` — a loja se matricula na nuvem e puxa tudo.

É o primeiro comando de uma instalação nova. Ele:

1. apresenta usuário, senha e conta à nuvem;
2. recebe o pacote de credenciais CIFRADO com o segredo de matrícula;
3. instala a identidade local (e grava o `.env`, se pedido);
4. a nuvem, do lado dela, já enfileirou a carga total para este nó.

Depois disso o `sync_worker` conecta e a carga desce sozinha. Rodar de novo
rematricula o MESMO nó (credencial nova, vínculo igual) — não cria um segundo.
"""
import getpass

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.synchronization.constants import NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import enrollment_client, guard


class Command(BaseCommand):
    help = "Matricula este backend local na nuvem e solicita a carga inicial."

    def add_arguments(self, parser):
        parser.add_argument("--api-url", dest="api_url", help="https://nuvem.exemplo.com")
        parser.add_argument("--username", help="superadmin ou admin da conta")
        parser.add_argument("--password", help="se omitido, é pedido sem eco")
        parser.add_argument("--account", help="UUID da conta")
        parser.add_argument("--secret", help="segredo de matrícula combinado")
        parser.add_argument("--node-name", dest="node_name", default="Servidor da loja")
        parser.add_argument("--restaurant", help="UUID do restaurante (opcional)")
        parser.add_argument("--wss-url", dest="wss_url", help="wss://.../ws/sync/v1/")
        parser.add_argument("--env-file", dest="env_file",
                            help="grava as credenciais neste arquivo (recomendado)")
        parser.add_argument("--force", action="store_true",
                            help="rematricula mesmo já havendo credencial")

    def handle(self, *args, **options):
        try:
            guard.ensure_environment()
        except guard.SyncDisabled as erro:
            raise CommandError(str(erro)) from erro

        if guard.node_type() != NodeType.LOCAL:
            raise CommandError("A matrícula é do nó LOCAL (SYNC_NODE_TYPE=local).")

        if enrollment_client.already_enrolled() and not options["force"]:
            self.stdout.write(self.style.WARNING(
                "Este nó já tem credencial. Use --force para rematricular."
            ))
            return

        dados = self._coletar(options)
        self.stdout.write(f"Matriculando em {dados['api_url']}…")
        try:
            pacote = enrollment_client.request_package(**dados)
        except enrollment_client.EnrollmentError as erro:
            raise CommandError(str(erro)) from erro

        proprio = enrollment_client.install(pacote, env_path=options.get("env_file"))
        self.stdout.write(self.style.SUCCESS(
            f"\nMatriculado. Nó local {proprio.id}, par {proprio.pair_id}."
        ))
        if pacote.get("SYNC_INITIAL_RUN_ID"):
            self.stdout.write(
                f"A nuvem enfileirou a carga total {pacote['SYNC_INITIAL_RUN_ID']}. "
                "Suba o `sync_worker` para recebê-la."
            )
        if not options.get("env_file"):
            self.stdout.write(self.style.WARNING(
                "Sem --env-file: a credencial vale só para este processo. "
                "Grave-a antes de reiniciar o container."
            ))

    def _coletar(self, options):
        api_url = options.get("api_url") or getattr(settings, "SYNC_CLOUD_API_URL", "")
        username = options.get("username") or getattr(settings, "SYNC_ENROLL_USERNAME", "")
        password = options.get("password") or getattr(settings, "SYNC_ENROLL_PASSWORD", "")
        account = options.get("account") or getattr(settings, "SYNC_ACCOUNT_ID", "")
        secret = options.get("secret") or getattr(settings, "SYNC_ENROLL_SECRET", "")
        wss = options.get("wss_url") or getattr(settings, "SYNC_CLOUD_WSS_URL", "")

        faltando = [n for n, v in
                    (("--api-url", api_url), ("--username", username), ("--account", account))
                    if not v]
        if faltando:
            raise CommandError("Faltam: " + ", ".join(faltando))
        if not password:
            password = getpass.getpass("Senha: ")
        if not secret:
            secret = getpass.getpass("Segredo de matrícula: ")

        existente = SyncNode.objects.filter(is_self=True, node_type=NodeType.LOCAL).first()
        return {
            "api_url": api_url,
            "username": username,
            "password": password,
            "account_id": account,
            "secret": secret,
            "node_name": options["node_name"],
            "restaurant_id": options.get("restaurant") or getattr(settings, "SYNC_STORE_ID", ""),
            "cloud_wss_url": wss,
            "existing_node_id": str(existente.id) if existente else None,
        }
