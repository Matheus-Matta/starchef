"""Com ACBrLib, quem emite a nota da venda de uma loja é a LOJA.

Cada instalação transmite com o seu comunicador. Se a nuvem também emitisse
— a venda recebida pela nuvem com a loja fora —, seriam dois emissores na
MESMA série, cada um com o seu contador: números repetidos e a segunda nota
recusada (ou pior, aceita). Então:

* a nuvem não emite pela ACBrLib a venda de uma conta que tem servidor de
  loja (`motivo_para_a_nuvem_nao_emitir`);
* a loja emite, sozinha, a nota dos pedidos pagos que chegaram pela
  sincronização sem nota (`emitir_pagos_sem_nota`, no Celery da loja).

Conta só-nuvem (sem servidor local) emite pela ACBrLib da nuvem normalmente.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.invoices.models import FiscalConfig

logger = logging.getLogger(__name__)

#: Até quando para trás a loja procura venda paga sem nota.
JANELA = timedelta(hours=48)


def _tipo_do_no():
    if not getattr(settings, "SYNC_ENABLED", False):
        return ""
    return str(getattr(settings, "SYNC_NODE_TYPE", "") or "").strip().lower()


def motivo_para_a_nuvem_nao_emitir(order, config):
    """Na nuvem, com ACBrLib e loja com servidor próprio: a nota é da loja."""
    if config.provider != FiscalConfig.PROVIDER_ACBRLIB or _tipo_do_no() != "cloud":
        return ""
    from django.db.models import Q

    from apps.synchronization.constants import NodeType
    from apps.synchronization.models import SyncNode

    tem_loja = SyncNode.objects.filter(
        Q(restaurant_id=order.restaurant_id) | Q(restaurant__isnull=True),
        account_id=order.account_id, node_type=NodeType.LOCAL, is_active=True,
    ).exists()
    return "A nota desta venda é emitida pelo servidor da loja (ACBrLib)." if tem_loja else ""


def emitir_pagos_sem_nota():
    """Na LOJA: emite a nota da venda paga que chegou sem nota. Devolve quantas."""
    if _tipo_do_no() != "local":
        return 0
    from apps.invoices.services import issue_invoice_for_paid_order
    from apps.orders.models import Order

    limite = timezone.now() - JANELA
    contas = FiscalConfig.all_objects.filter(
        provider=FiscalConfig.PROVIDER_ACBRLIB, is_active=True, deleted_at__isnull=True,
    ).values_list("restaurant_id", flat=True)
    pendentes = Order.all_objects.filter(
        restaurant_id__in=list(contas), status=Order.STATUS_PAID,
        updated_at__gte=limite, invoice__isnull=True,
    ).select_related("account", "restaurant", "branch")[:100]
    emitidas = 0
    for pedido in pendentes:
        try:
            if issue_invoice_for_paid_order(pedido, auto_print=True) is not None:
                emitidas += 1
        except Exception:  # noqa: BLE001 — um pedido não trava os outros
            logger.exception("Falha ao emitir a nota do pedido %s chegado sem nota", pedido.pk)
    return emitidas
