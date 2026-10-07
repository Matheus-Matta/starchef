"""Ajuste de estoque em lote: entrada, saída ou novo saldo, com motivo.

Cada linha vira um movimento de "Ajuste de inventário (+/-)" com o motivo e
quem fez — a trilha de auditoria é o próprio livro de movimentos. O lote é
uma transação só: uma linha inválida não deixa metade aplicada.

Concorrência: os insumos são travados em ordem de UUID e o saldo é relido
DEPOIS da trava. "Novo saldo = 7" calculado sobre um saldo lido antes da
trava gravaria a diferença errada se uma venda baixasse no meio.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.menu.models import Ingredient
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
        if not item.get("ingredient"):
            raise ValidationError(f"Linha {numero}: escolha o insumo.")
        linhas.append((str(item["ingredient"]), modo, _quantidade(item.get("quantity"), numero)))
    if not linhas:
        raise ValidationError("Inclua pelo menos um insumo no ajuste.")
    if len({ingrediente for ingrediente, _, _ in linhas}) != len(linhas):
        raise ValidationError("O mesmo insumo aparece mais de uma vez no lote.")
    return linhas


def apply_bulk_adjustment(*, location, user, reason, items):
    """Aplica o lote e devolve os movimentos criados."""
    motivo = (reason or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do ajuste: ele fica na auditoria.")
    linhas = _validar(items)

    with transaction.atomic():
        ids = sorted(ingrediente for ingrediente, _, _ in linhas)
        travados = {
            str(i.pk): i
            for i in Ingredient.objects.select_for_update().filter(pk__in=ids).order_by("pk")
        }
        faltando = set(ids) - set(travados)
        if faltando:
            raise ValidationError("Insumo não encontrado neste restaurante.")
        saldos = {
            str(row["ingredient_id"]): row["saldo"] or Decimal("0")
            for row in StockMovement.objects.filter(ingredient_id__in=ids, location=location)
            .values("ingredient_id").annotate(saldo=Sum("quantity"))
        }
        criados = []
        for ingrediente_id, modo, quantidade in linhas:
            insumo = travados[ingrediente_id]
            atual = saldos.get(ingrediente_id, Decimal("0"))
            delta = {"in": quantidade, "out": -quantidade, "set": quantidade - atual}[modo]
            if not delta:
                continue
            criados.append(StockMovement.objects.create(
                account=location.account, restaurant=location.restaurant, branch=location.branch,
                location=location, ingredient=insumo, operator=user,
                movement_type=(
                    StockMovement.TYPE_INVENTORY_ADJUSTMENT_POSITIVE if delta > 0
                    else StockMovement.TYPE_INVENTORY_ADJUSTMENT_NEGATIVE
                ),
                quantity=delta, stock_unit=insumo.unit,
                unit_cost=insumo.average_cost,
                # Com sinal, como o resto do livro: saída é custo negativo.
                total_cost=(delta * insumo.average_cost).quantize(CENTAVOS),
                reason=motivo,
                created_by=user, updated_by=user,
            ))
        for movimento in criados:
            record_audit(
                action=AuditLog.ACTION_CREATED, instance=movimento, actor=user, reason=motivo,
                metadata={"event": "stock_bulk_adjustment", "quantity": str(movimento.quantity)},
            )
    return criados
