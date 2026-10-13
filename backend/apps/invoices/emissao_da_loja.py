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

## Os dois pontos emitindo (`FiscalConfig.cloud_emission`)

Ligado no cadastro fiscal, a nuvem emite a venda FEITA NELA — o pedido na
faixa da nuvem (`orders/sequence_ranges.py`) — numa série só dela
(`cloud_series`, com contador próprio). A venda feita na loja continua da loja.

Série separada, e não "mandar o último número pela sincronização": com a loja
sem internet os dois lados não se enxergam, e um contador compartilhado
entregaria o mesmo número dos dois lados — justamente no dia em que a nuvem
mais emite. Série diferente não colide nunca, online ou offline. Dentro de
cada ponto a fila continua sendo a trava do cadastro (`select_for_update`).
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


def _tem_loja(order):
    from django.db.models import Q

    from apps.synchronization.constants import NodeType
    from apps.synchronization.models import SyncNode

    return SyncNode.objects.filter(
        Q(restaurant_id=order.restaurant_id) | Q(restaurant__isnull=True),
        account_id=order.account_id, node_type=NodeType.LOCAL, is_active=True,
    ).exists()


def _feita_na_nuvem(order):
    from apps.orders.sequence_ranges import PRIMEIRO_NUMERO_DA_NUVEM

    return (getattr(order, "sequence", None) or 0) >= PRIMEIRO_NUMERO_DA_NUVEM


def _nuvem_dividindo_com_a_loja(order, config):
    return (config.provider == FiscalConfig.PROVIDER_ACBRLIB and _tipo_do_no() == "cloud"
            and _tem_loja(order))


def motivo_para_a_nuvem_nao_emitir(order, config):
    """Na nuvem, com ACBrLib e loja com servidor próprio: a nota é da loja."""
    if not _nuvem_dividindo_com_a_loja(order, config):
        return ""
    if not getattr(config, "cloud_emission", False):
        return ("A nota desta venda é emitida pelo servidor da loja (ACBrLib). Para a nuvem "
                "emitir as vendas feitas nela, ligue \"A nuvem também emite\" no cadastro fiscal.")
    if not _feita_na_nuvem(order):
        return "Venda feita na loja: a nota é emitida pelo servidor da loja (ACBrLib)."
    return ""


def serie_desta_emissao(order, config):
    """`(série, campo do contador)` em que ESTE servidor numera a nota."""
    if (getattr(config, "cloud_emission", False) and config.cloud_series
            and _nuvem_dividindo_com_a_loja(order, config)):
        return config.cloud_series, "cloud_next_number"
    return config.series, "next_number"


def avancar_contador(config, campo, numero):
    setattr(config, campo, numero + 1)
    config.save(update_fields=[campo, "updated_at"])


def erro_da_serie_da_nuvem(attrs, instance):
    """A mesma série nos dois pontos é número repetido na SEFAZ (400, não 500)."""
    def valor(campo, padrao=None):
        return attrs.get(campo, getattr(instance, campo, padrao))

    if not valor("cloud_emission", False):
        return ""
    serie_da_nuvem = valor("cloud_series")
    if not serie_da_nuvem:
        return "Informe a serie da nuvem para ela tambem emitir."
    if serie_da_nuvem == valor("series", 1):
        return "A serie da nuvem precisa ser diferente da serie da loja."
    return ""


def emitir_pagos_sem_nota():
    """Na LOJA: emite a nota da venda paga que chegou sem nota. Devolve quantas."""
    if _tipo_do_no() != "local":
        return 0
    from apps.invoices.services import issue_invoice_for_paid_order
    from apps.orders.models import Order

    limite = timezone.now() - JANELA
    from django.db.models import Q

    from apps.orders.sequence_ranges import PRIMEIRO_NUMERO_DA_NUVEM

    configs = FiscalConfig.all_objects.filter(
        provider=FiscalConfig.PROVIDER_ACBRLIB, is_active=True, deleted_at__isnull=True,
    )
    contas = configs.values_list("restaurant_id", flat=True)
    # Com os dois pontos emitindo, a venda feita na nuvem é da nuvem: ela chega
    # aqui paga e ainda sem nota (a nota vem atrás), e varrê-la daria duas.
    nuvem_emite = configs.filter(cloud_emission=True).values_list("restaurant_id", flat=True)
    pendentes = Order.all_objects.filter(
        restaurant_id__in=list(contas), status=Order.STATUS_PAID,
        updated_at__gte=limite, invoice__isnull=True,
    ).exclude(
        Q(restaurant_id__in=list(nuvem_emite)) & Q(sequence__gte=PRIMEIRO_NUMERO_DA_NUVEM),
    ).select_related("account", "restaurant", "branch")[:100]
    emitidas = 0
    for pedido in pendentes:
        try:
            if issue_invoice_for_paid_order(pedido, auto_print=True) is not None:
                emitidas += 1
        except Exception:  # noqa: BLE001 — um pedido não trava os outros
            logger.exception("Falha ao emitir a nota do pedido %s chegado sem nota", pedido.pk)
    return emitidas
