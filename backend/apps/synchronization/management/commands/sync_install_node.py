"""`manage.py sync_install_node` — instala o pacote da nuvem no backend da LOJA.

Cria o SyncNode próprio (is_self) e o registro do peer da nuvem, com os IDs que
a nuvem gerou. Sem isso o worker sobe e não sabe quem ele é.
"""
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Account
from apps.synchronization.constants import NodeStatus, NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import guard, nodes


class Command(BaseCommand):
    help = "Cria a identidade local a partir do pacote gerado na nuvem."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="Servidor da loja")

    def handle(self, *args, **options):
        try:
            guard.ensure_enabled()
        except guard.SyncDisabled as erro:
            raise CommandError(str(erro)) from erro

        if guard.node_type() != NodeType.LOCAL:
            raise CommandError("Este comando roda no nó LOCAL (SYNC_NODE_TYPE=local).")

        node_id = getattr(settings, "SYNC_NODE_ID", "")
        pair_id = getattr(settings, "SYNC_PAIR_ID", "")
        account_id = getattr(settings, "SYNC_ACCOUNT_ID", "")
        peer_id = getattr(settings, "SYNC_PEER_NODE_ID", "")
        if not (node_id and pair_id and account_id):
            raise CommandError(
                "Faltam SYNC_NODE_ID, SYNC_PAIR_ID ou SYNC_ACCOUNT_ID no .env.local."
            )

        conta = Account.objects.filter(pk=account_id).first()
        if conta is None:
            raise CommandError(
                f"A conta {account_id} ainda não existe neste banco. Rode primeiro a "
                "carga de dados essenciais pelo Admin da nuvem, ou crie a conta."
            )

        proprio = self._criar(node_id, pair_id, conta, NodeType.LOCAL, options["name"], is_self=True)
        if peer_id:
            par = self._criar(peer_id, pair_id, conta, NodeType.CLOUD, "Nuvem", is_self=False)
            proprio.peer = par
            proprio.save(update_fields=["peer", "updated_at"])
        nodes.invalidate_cache()

        self.stdout.write(self.style.SUCCESS(
            f"Identidade local pronta: nó {proprio.id}, par {proprio.pair_id}."
        ))

    def _criar(self, node_id, pair_id, conta, node_type, nome, *, is_self):
        no, criado = SyncNode.objects.update_or_create(
            pk=uuid.UUID(str(node_id)),
            defaults={
                "pair_id": uuid.UUID(str(pair_id)),
                "account": conta,
                "node_type": node_type,
                "environment": guard.current_environment(),
                "name": nome,
                "status": NodeStatus.ACTIVE if is_self else NodeStatus.PENDING,
                "is_self": is_self,
                "is_active": True,
            },
        )
        self.stdout.write(f"  {'criado' if criado else 'atualizado'}: {no.id} ({node_type})")
        return no
