"""Cálculos financeiros usados nos comprovantes de fechamento de caixa."""

from decimal import Decimal

from django.db.models import Q

from apps.payments.models import CashMovement, Payment
from apps.printers.services import _linha_valor

_FORMAS_PRINCIPAIS = ["cash", "card:credit", "card:debit", "pix", "voucher"]
_FORMAS_EXTRAS = ["card", "other"]
_ROTULO_FORMAS = {
    "cash": "Dinheiro",
    "card:credit": "Cartao credito",
    "card:debit": "Cartao debito",
    "card": "Cartao sem tipo",
    "pix": "PIX",
    "voucher": "Vale/voucher",
    "other": "Outras formas",
}


def gaveta(session):
    """Resume somente o que entrou e saiu da gaveta física."""
    abertura = suprimentos = sangrias = troco = estornos = vendas = 0
    tem_abertura = False
    for movimento in session.movements.all():
        if movimento.status != "approved":
            continue
        centavos = int((abs(Decimal(movimento.amount)) * 100).to_integral_value())
        if movimento.movement_type == CashMovement.TYPE_OPENING:
            abertura += centavos
            tem_abertura = True
        elif movimento.movement_type == CashMovement.TYPE_SALE:
            vendas += centavos
        elif movimento.movement_type == CashMovement.TYPE_SUPPLY:
            suprimentos += centavos
        elif movimento.movement_type == CashMovement.TYPE_WITHDRAWAL:
            if movimento.payment_id:
                troco += centavos
            else:
                sangrias += centavos
        elif movimento.movement_type == CashMovement.TYPE_REFUND:
            estornos += centavos
    if not tem_abertura:
        abertura = int((Decimal(session.opening_amount or 0) * 100).to_integral_value())
    return {
        "abertura": abertura,
        "vendas": vendas,
        "suprimentos": suprimentos,
        "sangrias": sangrias,
        "troco": troco,
        "estornos": estornos,
        "esperado": _em_centavos(session.expected_amount),
        "contado": _em_centavos(session.actual_amount),
        "diferenca": _em_centavos(session.difference_amount),
    }


def vendas_por_forma(session):
    """Agrupa os recebimentos e sempre exibe as cinco formas principais."""
    recebimentos = (
        Payment.objects.filter(status=Payment.STATUS_APPROVED)
        .filter(Q(metadata__cash_register=str(session.pk)) | Q(cash_movements__cash_register_id=session.pk))
        .select_related("payment_method")
        .distinct()
    )
    totais = {}
    total = 0
    for recebimento in recebimentos:
        tipo = (recebimento.payment_method.method_type or "other").strip().lower()
        subtipo = (recebimento.card_subtype or "").strip().lower()
        chave = f"card:{subtipo}" if tipo == "card" and subtipo else tipo
        if chave not in _ROTULO_FORMAS:
            chave = "other"
        centavos = _em_centavos(recebimento.amount)
        totais[chave] = totais.get(chave, 0) + centavos
        total += centavos
    chaves = [*_FORMAS_PRINCIPAIS, *[chave for chave in _FORMAS_EXTRAS if totais.get(chave)]]
    return {
        "linhas": [(_ROTULO_FORMAS[chave], totais.get(chave, 0)) for chave in chaves],
        "total": total,
        "dinheiro": totais.get("cash", 0),
        "quantidade": recebimentos.count(),
    }


def linha_centavos(rotulo, centavos):
    return _linha_valor(rotulo, f"{Decimal(centavos) / 100:.2f}")


def _em_centavos(valor):
    return int((Decimal(valor or 0) * 100).to_integral_value())
