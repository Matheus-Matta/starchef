"""Só UM servidor baixa o cardápio: senão o estoque sai em dobro.

Loja e nuvem têm o mesmo cadastro (sincronização) e o mesmo agendador. Se os
dois executassem, cada um criaria a sua saída — com ids diferentes, as duas
sincronizariam e o arroz sairia duas vezes. A regra é a da nota fiscal
(`invoices/emissao_da_loja.py`): com servidor de loja, quem baixa é a loja
(é lá que o estoque físico está); conta só-nuvem, a nuvem.
"""
from django.conf import settings
from django.db.models import Q


def _tipo_do_no():
    if not getattr(settings, "SYNC_ENABLED", False):
        return ""
    return str(getattr(settings, "SYNC_NODE_TYPE", "") or "").strip().lower()


def este_servidor_executa(cardapio):
    if _tipo_do_no() != "cloud":
        return True
    from apps.synchronization.constants import NodeType
    from apps.synchronization.models import SyncNode

    return not SyncNode.objects.filter(
        Q(restaurant_id=cardapio.restaurant_id) | Q(restaurant__isnull=True),
        account_id=cardapio.account_id, node_type=NodeType.LOCAL, is_active=True,
    ).exists()
