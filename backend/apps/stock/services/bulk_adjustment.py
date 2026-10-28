"""Ajuste de estoque em lote: entrada, saída ou novo saldo, com motivo.

Cada linha vira um movimento de "Ajuste de inventário (+/-)" com o motivo e
quem fez — a trilha de auditoria é o próprio livro de movimentos. O lote é
uma transação só: uma linha inválida não deixa metade aplicada.

Concorrência: produtos e insumos são travados em ordem de UUID e o saldo é relido
DEPOIS da trava. "Novo saldo = 7" calculado sobre um saldo lido antes da
trava gravaria a diferença errada se uma venda baixasse no meio.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.menu.models import Ingredient, Product
from apps.stock.models import StockMovement

MODOS = {"in", "out", "set"}
CENTAVOS = Decimal("0.01")


def _quantidade(valor, linha):
    try:
        quantidade = Decimal(str(valor))
    except (InvalidOperation, TypeError):
        raise ValidationError(f"Linha {linha}: quantidade inválida.") from None
    if quantidade < 0:
        raise ValidationError(f"Linha {linha}: a quantidade não pode ser negativa.")
    return quantidade


def _validar(itens):
    linhas = []
    for numero, item in enumerate(itens or [], start=1):
        modo = str(item.get("mode") or "")
        if modo not in MODOS:
            raise ValidationError(f"Linha {numero}: use entrada, saída ou novo saldo.")
        alvos = [(tipo, item.get(tipo)) for tipo in ("ingredient", "product") if item.get(tipo)]
        if len(alvos) != 1:
            raise ValidationError(f"Linha {numero}: escolha um produto ou insumo.")
        tipo, alvo_id = alvos[0]
        linhas.append((tipo, str(alvo_id), modo, _quantidade(item.get("quantity"), numero)))
    if not linhas:
        raise ValidationError("Inclua pelo menos um item no ajuste.")
    if len({(tipo, alvo_id) for tipo, alvo_id, _, _ in linhas}) != len(linhas):
        raise ValidationError("O mesmo item aparece mais de uma vez no lote.")
    return linhas


def _travar_itens(linhas):
    ingredientes = sorted(alvo_id for tipo, alvo_id, _, _ in linhas if tipo == "ingredient")
    produtos = sorted(alvo_id for tipo, alvo_id, _, _ in linhas if tipo == "product")
    travados = {
        ("ingredient", str(item.pk)): item
        for item in Ingredient.objects.select_for_update().filter(pk__in=ingredientes).order_by("pk")
    }
    travados.update({
        ("product", str(item.pk)): item
        for item in Product.objects.select_for_update().filter(pk__in=produtos).order_by("pk")
    })
    esperados = {(tipo, alvo_id) for tipo, alvo_id, _, _ in linhas}
    if esperados - set(travados):
        raise ValidationError("Produto ou insumo não encontrado neste restaurante.")
    return travados


def _saldos(location, linhas):
    saldos = {}
    for tipo in ("ingredient", "product"):
        ids = [alvo_id for tipo_linha, alvo_id, _, _ in linhas if tipo_linha == tipo]
        for row in (
            StockMovement.objects.filter(**{f"{tipo}_id__in": ids}, location=location)
            .values(f"{tipo}_id").annotate(saldo=Sum("quantity"))
        ):
            saldos[(tipo, str(row[f"{tipo}_id"]))] = row["saldo"] or Decimal("0")
    return saldos


def apply_bulk_adjustment(*, location, user, reason, items):
    """Aplica o lote e devolve os movimentos criados."""
    motivo = (reason or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do ajuste: ele fica na auditoria.")
    linhas = _validar(items)

    with transaction.atomic():
        travados = _travar_itens(linhas)
        saldos = _saldos(location, linhas)
        criados = []
        for tipo, alvo_id, modo, quantidade in linhas:
            item = travados[(tipo, alvo_id)]
            atual = saldos.get((tipo, alvo_id), Decimal("0"))
            delta = {"in": quantidade, "out": -quantidade, "set": quantidade - atual}[modo]
            if not delta:
                continue
            custo = item.average_cost if tipo == "ingredient" else item.current_average_cost
            unidade = item.unit if tipo == "ingredient" else item.stock_unit
            criados.append(StockMovement.objects.create(
                account=location.account, restaurant=location.restaurant, branch=location.branch,
                location=location, operator=user, **{tipo: item},
                movement_type=(
                    StockMovement.TYPE_INVENTORY_ADJUSTMENT_POSITIVE if delta > 0
                    else StockMovement.TYPE_INVENTORY_ADJUSTMENT_NEGATIVE
                ),
                quantity=delta, stock_unit=unidade,
                unit_cost=custo,
                # Com sinal, como o resto do livro: saída é custo negativo.
                total_cost=(delta * custo).quantize(CENTAVOS),
                reason=motivo,
                created_by=user, updated_by=user,
            ))
        for movimento in criados:
            record_audit(
                action=AuditLog.ACTION_CREATED, instance=movimento, actor=user, reason=motivo,
                metadata={"event": "stock_bulk_adjustment", "quantity": str(movimento.quantity)},
            )
    return criados
