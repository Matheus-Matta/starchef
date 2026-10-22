"""Vendas do período: totais, formas de pagamento e o gráfico.

Venda é pedido PAGO aberto no período (a mesma régua do relatório de vendas).
As formas de pagamento somam o que entrou no período (`paid_at`), já sem o
troco — é o que o caixa confere contra a maquininha.
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.reports.comandas_agora import reais
from apps.reports.visao_geral_periodo import DIA, faixa

ZERO = Decimal("0.00")


def totais(pedidos, order_model):
    pago = Q(payment_status=order_model.PAYMENT_PAID)
    linha = pedidos.aggregate(
        pedidos=Count("id"),
        pagos=Count("id", filter=pago),
        abertos=Count("id", filter=Q(status__in=[order_model.STATUS_OPEN,
                                                 order_model.STATUS_AWAITING_PAYMENT])),
        cancelados=Count("id", filter=Q(status=order_model.STATUS_CANCELLED)),
        vendido=Sum("total", filter=pago),
        descontos=Sum("discount", filter=pago),
        taxa_servico=Sum("service_fee", filter=pago),
    )
    pagos, vendido = linha["pagos"] or 0, reais(linha["vendido"])
    return {
        "vendido": vendido,
        "pedidos": linha["pedidos"] or 0,
        "pedidos_pagos": pagos,
        "pedidos_abertos": linha["abertos"] or 0,
        "pedidos_cancelados": linha["cancelados"] or 0,
        "ticket_medio": reais(vendido / pagos) if pagos else ZERO,
        "descontos": reais(linha["descontos"]),
        "taxa_servico": reais(linha["taxa_servico"]),
    }


ROTULO_DO_TIPO = {"cash": "Dinheiro", "pix": "PIX", "voucher": "Vale", "other": "Outros"}
ROTULO_DO_CARTAO = {"credit": "Crédito", "debit": "Débito"}


def _rotulo(linha):
    tipo = linha["payment_method__method_type"]
    if tipo == "card":
        return f"Cartão {ROTULO_DO_CARTAO.get(linha['card_subtype'], '')}".strip()
    return ROTULO_DO_TIPO.get(tipo) or linha["payment_method__name"] or "Outros"


def formas_de_pagamento(pagamentos):
    """Cada forma com valor e quantidade, da maior para a menor. Zeradas saem."""
    linhas = (pagamentos.values("payment_method__method_type", "payment_method__name", "card_subtype")
              .annotate(valor=Sum("amount"), quantidade=Count("id")))
    por_rotulo = {}
    for linha in linhas:
        item = por_rotulo.setdefault(_rotulo(linha), {"forma": _rotulo(linha), "valor": ZERO, "quantidade": 0})
        item["valor"] += linha["valor"] or ZERO
        item["quantidade"] += linha["quantidade"]
    formas = [f for f in por_rotulo.values() if f["valor"] > 0]
    return sorted(({**f, "valor": reais(f["valor"])} for f in formas), key=lambda f: -f["valor"])


def grafico(pagos, nome_do_periodo, primeiro, ultimo):
    """Hoje: por hora com venda. Semana/mês: por dia. Barras zeradas saem."""
    por_chave = {}
    for aberto_em, total in pagos.filter(**faixa("opened_at", primeiro, ultimo)).values_list(
            "opened_at", "total"):
        local = timezone.localtime(aberto_em)
        chave = local.hour if nome_do_periodo == DIA else local.date()
        por_chave[chave] = por_chave.get(chave, ZERO) + (total or ZERO)
    if nome_do_periodo == DIA:
        return [{"rotulo": f"{hora:02d}h", "valor": reais(valor)}
                for hora, valor in sorted(por_chave.items()) if valor > 0]
    return [{"rotulo": dia.strftime("%d/%m"), "data": dia.isoformat(), "valor": reais(valor)}
            for dia, valor in sorted(por_chave.items()) if valor > 0]
