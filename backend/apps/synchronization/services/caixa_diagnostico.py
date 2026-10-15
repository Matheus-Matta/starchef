"""O histórico do caixa na sincronização: onde parou, e mandar de novo.

O valor final do caixa chega numa linha só (a sessão); o histórico —
abertura, venda em dinheiro, troco, suprimento, sangria, fechamento — são
linhas à parte, cada uma com o seu evento. Um evento preso (esperando o pai,
virado conflito, descartado) some do extrato do outro lado sem mudar o total.

* `diagnostico` lê, NESTE servidor, os eventos do caixa do período e o que
  ficou pelo caminho. Roda na loja (saída) e na nuvem (entrada).
* `reenviar` gera de novo, na loja, os eventos das sessões do período, na
  ordem que o destino precisa. É seguro: o que o outro lado já tem chega com
  a mesma versão e é ignorado; o que falta entra.
"""
from collections import Counter
from datetime import timedelta

from django.utils import timezone

from apps.synchronization.constants import EventStatus

TIPOS_DO_CAIXA = ("cash_register", "cash_movement", "payment", "order", "order_item")
_RESOLVIDOS = {EventStatus.APPLIED, EventStatus.ACKNOWLEDGED}


class SoNaLoja(Exception):
    """Reenviar é da origem: na nuvem não há o que a loja tem e a nuvem não."""


def _desde(dias):
    return timezone.now() - timedelta(days=dias)


def diagnostico(*, dias):
    from apps.synchronization.models import SyncConflict, SyncDiscard, SyncEvent

    desde = _desde(dias)
    eventos = SyncEvent.objects.filter(entity_type__in=TIPOS_DO_CAIXA, created_at__gte=desde)
    contagem = Counter(eventos.values_list("direction", "entity_type", "status"))
    parados = list(
        eventos.exclude(status__in=_RESOLVIDOS)
        .order_by("sequence")
        .values("direction", "entity_type", "entity_id", "status", "attempts", "last_error")[:200]
    )
    conflitos = list(
        SyncConflict.objects.filter(entity_type__in=TIPOS_DO_CAIXA, created_at__gte=desde)
        .values("entity_type", "entity_id", "status")[:100]
    )
    descartes = list(
        SyncDiscard.objects.filter(entity_type__in=TIPOS_DO_CAIXA, created_at__gte=desde)
        .values("entity_type", "entity_id", "motivo")[:100]
    )
    return {"contagem": contagem, "parados": parados, "conflitos": conflitos, "descartes": descartes}


def reenviar(*, dias=None, sessao=None):
    """Gera de novo os eventos das sessões. Devolve quantos eventos saíram."""
    from apps.core.tenant import tenant_context
    from apps.payments.models import CashRegister
    from apps.synchronization.services import nodes

    if nodes.is_cloud():
        raise SoNaLoja("Rode --reenviar no servidor da LOJA: é ela quem tem o que falta na nuvem.")
    sessoes = CashRegister.all_objects.filter(deleted_at__isnull=True)
    sessoes = sessoes.filter(pk=sessao) if sessao else sessoes.filter(opened_at__gte=_desde(dias or 7))
    total = 0
    for registro in sessoes.select_related("account").order_by("opened_at"):
        with tenant_context(registro.account):
            total += _reenviar_sessao(registro)
    return total


def _reenviar_sessao(registro):
    from django.db.models import Q

    from apps.orders.models import Order, OrderItem
    from apps.payments.models import CashMovement, Payment

    movimentos = list(CashMovement.all_objects.filter(cash_register=registro).order_by("created_at"))
    pagamentos = list(
        Payment.all_objects.filter(
            Q(metadata__cash_register=str(registro.pk)) | Q(cash_movements__cash_register=registro)
        ).distinct().order_by("paid_at")
    )
    pedidos = list(Order.all_objects.filter(pk__in={p.order_id for p in pagamentos}).order_by("opened_at"))
    itens = list(OrderItem.all_objects.filter(order__in=pedidos).order_by("created_at"))
    # A ordem é a das dependências no destino: a sessão, os pedidos e seus
    # itens, os recebimentos (apontam para o pedido) e por fim os movimentos
    # (a venda em dinheiro e o troco apontam para o recebimento).
    return sum(len(_registrar(linha)) for linha in [registro, *pedidos, *itens, *pagamentos, *movimentos])


def _registrar(instancia):
    from apps.synchronization.constants import Operation
    from apps.synchronization.services import outbox

    return outbox.record(instancia, Operation.UPSERT, force=True)
