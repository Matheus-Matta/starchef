"""Os caixas abertos AGORA e quanto cada gaveta deve ter.

O saldo é a soma dos movimentos aprovados da sessão — a mesma conta do
fechamento (`payments.services.close_cash_register`): abertura + vendas em
dinheiro + suprimentos − sangrias − estornos. Não depende do período escolhido
na tela: caixa aberto é estado de agora.
"""
from decimal import Decimal

from django.db.models import Q, Sum

from apps.reports.comandas_agora import reais

ZERO = Decimal("0.00")


def caixas_abertos(escopo):
    from apps.payments.models import CASH_REGISTER_FINAL_STATUSES, CashMovement, CashRegister

    def soma(tipo):
        return Sum("movements__amount", filter=Q(movements__status="approved",
                                                 movements__movement_type=tipo))

    sessoes = (
        CashRegister.objects.filter(**escopo).exclude(status__in=CASH_REGISTER_FINAL_STATUSES)
        .select_related("cash_station", "opened_by")
        .annotate(
            saldo=Sum("movements__amount", filter=Q(movements__status="approved")),
            vendas=soma(CashMovement.TYPE_SALE),
            sangrias=soma(CashMovement.TYPE_WITHDRAWAL),
            suprimentos=soma(CashMovement.TYPE_SUPPLY),
        )
        .order_by("opened_at")
    )
    caixas = []
    for sessao in sessoes:
        operador = sessao.opened_by
        caixas.append({
            "id": str(sessao.pk),
            "caixa": sessao.cash_station.name if sessao.cash_station_id else sessao.station,
            "operador": (operador.get_full_name() or operador.get_username()) if operador else "",
            "aberto_em": sessao.opened_at,
            "status": sessao.status,
            "abertura": reais(sessao.opening_amount),
            "vendas_em_dinheiro": reais(sessao.vendas),
            "sangrias": reais(abs(sessao.sangrias or ZERO)),
            "suprimentos": reais(sessao.suprimentos),
            "saldo": reais(sessao.saldo),
        })
    return caixas
