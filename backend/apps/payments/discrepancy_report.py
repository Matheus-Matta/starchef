"""Relatório de divergências das sessões de caixa selecionadas.

Para cada sessão: o que o PDV registrou (por forma de pagamento), o que foi
registrado como divergência e o total recebido — a soma dos dois. As
canceladas ficam de fora da conta e aparecem na lista, para auditoria.

EM LOTE: três consultas para o relatório inteiro (sessões, pagamentos,
divergências), qualquer que seja o número de sessões. Perguntar sessão a
sessão seria uma ida ao banco por caixa — e é justamente no fim de um dia
cheio, com muitos caixas, que o gerente abre isto.
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q

from apps.payments.discrepancy import SalesDiscrepancy
from apps.payments.models import Payment
from apps.payments.terminals import operator_label

ZERO = Decimal("0.00")
#: Teto de sessões por relatório: é conferência de período, não exportação.
MAXIMO_DE_SESSOES = 100


def _por_forma(linhas):
    """[(id, nome, tipo, valor)] -> lista ordenada por nome, somando a mesma forma."""
    soma = {}
    for forma_id, nome, tipo, valor in linhas:
        atual = soma.get(forma_id) or {"payment_method": forma_id, "name": nome, "method_type": tipo, "amount": ZERO}
        atual["amount"] += Decimal(str(valor))
        soma[forma_id] = atual
    return sorted(soma.values(), key=lambda f: (f["name"] or "").lower())


def _vendas_por_sessao(ids):
    """Pagamentos aprovados de todas as sessões, numa consulta só.

    O vínculo é o mesmo do extrato: `metadata.cash_register` gravado no
    recebimento, ou o movimento de caixa que aponta o pagamento (antigos).
    """
    textos = [str(i) for i in ids]
    linhas = (
        Payment.objects.filter(status=Payment.STATUS_APPROVED)
        .filter(Q(metadata__cash_register__in=textos) | Q(cash_movements__cash_register_id__in=ids))
        .values_list(
            "pk", "amount", "payment_method_id", "payment_method__name",
            "payment_method__method_type", "metadata__cash_register", "cash_movements__cash_register_id",
        )
    )
    vistos, por_sessao = set(), defaultdict(list)
    for pk, valor, forma, nome, tipo, pela_metadata, pelo_movimento in linhas:
        sessao = pela_metadata if pela_metadata in textos else (str(pelo_movimento) if pelo_movimento else None)
        # O JOIN com movimentos repete o pagamento; conta uma vez só.
        if sessao is None or pk in vistos:
            continue
        vistos.add(pk)
        por_sessao[sessao].append((str(forma), nome, tipo, valor))
    return por_sessao


def _total(formas):
    return sum((f["amount"] for f in formas), ZERO)


def relatorio(sessoes):
    """`sessoes`: queryset JÁ escopado pelo tenant e filtrado pelos ids pedidos."""
    sessoes = list(sessoes.select_related("cash_station", "opened_by").order_by("opened_at"))
    ids = [s.pk for s in sessoes]
    vendas = _vendas_por_sessao(ids)
    divergencias = defaultdict(list)
    for d in SalesDiscrepancy.objects.filter(cash_register_id__in=ids).select_related("created_by"):
        divergencias[str(d.cash_register_id)].append(d)

    linhas, todas_vendas, todas_divergencias = [], [], []
    for sessao in sessoes:
        chave = str(sessao.pk)
        registradas = _por_forma(vendas.get(chave, []))
        contadas = [d for d in divergencias.get(chave, []) if d.status in SalesDiscrepancy.COUNTED_STATUSES]
        divergentes = _por_forma(
            (f["payment_method"], f["name"], f["method_type"], f["amount"])
            for d in contadas for f in d.by_payment_method
        )
        todas_vendas += vendas.get(chave, [])
        todas_divergencias += [
            (f["payment_method"], f["name"], f["method_type"], f["amount"])
            for d in contadas for f in d.by_payment_method
        ]
        linhas.append({
            "cash_register": chave,
            "cash_station_name": sessao.cash_station.name if sessao.cash_station_id else sessao.station,
            "operator_name": operator_label(sessao.opened_by),
            "opened_at": sessao.opened_at,
            "closed_at": sessao.closed_at,
            "status": sessao.status,
            "drawer_difference": sessao.difference_amount,
            "registered_sales": _total(registradas),
            "registered_by_method": registradas,
            "discrepancy_total": _total(divergentes),
            "discrepancy_by_method": divergentes,
            "received_total": _total(registradas) + _total(divergentes),
            "discrepancies": [_resumo(d) for d in divergencias.get(chave, [])],
        })
    registradas, divergentes = _por_forma(todas_vendas), _por_forma(todas_divergencias)
    return {
        "sessions": linhas,
        "totals": {
            "registered_sales": _total(registradas),
            "registered_by_method": registradas,
            "discrepancy_total": _total(divergentes),
            "discrepancy_by_method": divergentes,
            "received_total": _total(registradas) + _total(divergentes),
            "open_count": sum(len([d for d in divergencias.get(str(i), []) if d.status == "open"]) for i in ids),
        },
    }


def _resumo(d):
    return {
        "id": str(d.pk), "amount": d.amount, "status": d.status, "reason": d.reason,
        "notes": d.notes, "payment_methods": d.by_payment_method, "created_at": d.created_at,
        "created_by_name": operator_label(d.created_by) if d.created_by_id else "",
        "regularization_note": d.regularization_note, "cancel_reason": d.cancel_reason,
    }
