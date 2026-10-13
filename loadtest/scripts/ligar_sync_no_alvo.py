"""Matricula uma loja de mentira no alvo de carga, para a venda gerar eventos.

Na nuvem com loja matriculada, cada registro salvo vira um evento de saída
(`synchronization/services/outbox.py`). Sem um nó "nuvem" (este) e um nó
"loja" ativo da conta, o alvo de carga não paga esse custo e mede menos do
que a produção. Rode dentro do container, com LOADTEST_SYNC=true:

    docker compose -f docker/loadtest/docker-compose.yml exec -T backend \
        python manage.py shell < loadtest/scripts/ligar_sync_no_alvo.py
"""
import uuid

from apps.accounts.models import Account
from apps.synchronization.constants import NodeStatus, NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import nodes
from apps.synchronization.services.provisioning import ensure_self_node

primeira = Account.objects.order_by("created_at").first()
ensure_self_node(account=primeira, node_type=NodeType.CLOUD, pair_id=uuid.uuid4(), name="Nuvem (carga)")
for conta in Account.objects.all():
    SyncNode.objects.get_or_create(
        account=conta, node_type=NodeType.LOCAL, name=f"Loja de carga {conta.pk}",
        defaults={"pair_id": uuid.uuid4(), "status": NodeStatus.ACTIVE, "is_active": True},
    )
nodes.invalidate_cache()
print("nós:", SyncNode.objects.count(), "| self:", nodes.self_node_or_none())
