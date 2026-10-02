"""Zerar comandas em lote: retira o que está aberto e devolve o cartão.

Zerar NÃO apaga: cada anotação aberta é cancelada por `void_command_item` — o
mesmo caminho do cancelamento unitário, com motivo, prazo do restaurante,
autorização e auditoria — e continua no histórico da comanda. Depois o cartão
volta livre por `free_command_if_empty`, que também solta a mesa.

Cada comanda tem a própria transação, travada antes de ler: a recusa de uma não
desfaz as outras, e uma comanda nunca fica pela metade (se um item precisa de
autorização que não veio, os itens dela que já tinham saído voltam).
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context

#: Teto por chamada: zerar é gesto de fim de dia, não de migração.
MAXIMO = 500


def zerar_do_request(request, visiveis):
    """O lote do endpoint: só o que o usuário enxerga, autorizado por restaurante.

    A senha do caixa (ou o login do supervisor) é conferida uma vez por
    restaurante, como no cancelamento em massa de pedidos. Id fora do escopo
    do usuário volta como "não encontrada", sem dizer se existe em outra conta.
    """
    from apps.orders.views import _can_authorize_cancellation
    from apps.restaurants.models import Restaurant

    ids = request.data.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > MAXIMO:
        raise ValidationError({"ids": f"Selecione de 1 a {MAXIMO} comandas."})
    ids = list(dict.fromkeys(str(i) for i in ids))
    # Só UUID vai ao banco: `None`, número ou texto qualquer no `pk__in`
    # estourava ValidationError do Django dentro da consulta — 500 por um id
    # torto no meio de uma lista boa. Os tortos voltam como "não encontrada".
    validos = [i for i in ids if _e_uuid(i)]
    por_restaurante = {}
    for comanda_id, restaurante_id in visiveis.filter(pk__in=validos).values_list("pk", "restaurant_id"):
        por_restaurante.setdefault(restaurante_id, []).append(str(comanda_id))

    # ZERAR É CANCELAMENTO EM MASSA. Tirar UM item no prazo é gesto de quem
    # lançou (o garçom corrige o próprio engano); esvaziar várias comandas de
    # uma vez é perda no relatório. Sem a permissão de cancelar (gerente e
    # admin), só com a senha de operação ou o login de um supervisor.
    from apps.core.access import is_tenant_admin
    from apps.core.permissions import effective_permission_codes
    from apps.restaurants.models import Command

    codigos = effective_permission_codes(request.user)
    pode_cancelar = is_tenant_admin(request.user) or "*" in codigos or "orders.cancel" in codigos

    resultado = {"reset": [], "skipped": []}
    for restaurante_id, grupo in por_restaurante.items():
        restaurante = Restaurant.objects.get(pk=restaurante_id)
        autorizado, quem, _como = _can_authorize_cancellation(request, restaurante, restaurante.account_id)
        if not (pode_cancelar or autorizado):
            numeros = {str(pk): n for pk, n in Command.objects.filter(pk__in=grupo).values_list("pk", "number")}
            resultado["skipped"] += [
                {"id": i, "number": numeros.get(i), "reason": (
                    "Zerar comandas exige gerente: informe a senha de operação ou o login de um supervisor."
                )}
                for i in grupo
            ]
            continue
        parcial = zerar_comandas(
            grupo, account=restaurante.account, user=request.user, reason=request.data.get("reason"),
            authorized=autorizado, authorized_by=quem,
        )
        resultado["reset"] += parcial["reset"]
        resultado["skipped"] += parcial["skipped"]
    conhecidas = {i for grupo in por_restaurante.values() for i in grupo}
    resultado["skipped"] += [
        {"id": i, "number": None, "reason": "Comanda não encontrada."} for i in ids if i not in conhecidas
    ]
    return resultado


def _e_uuid(valor):
    import uuid

    try:
        uuid.UUID(str(valor))
    except ValueError:
        return False
    return True


def zerar_comandas(ids, *, account, user, reason, authorized=False, authorized_by=None):
    """Devolve `{"reset": [...], "skipped": [...]}`, um registro por id pedido."""
    from apps.orders.item_cancellation import CancelamentoBloqueado
    from apps.restaurants.models import Command

    if reason is not None and not isinstance(reason, str):
        raise ValidationError("O motivo é um texto.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Informe o motivo para zerar as comandas.")

    resultado = {"reset": [], "skipped": []}
    with tenant_context(account):
        conhecidas = {str(c.pk): c.number for c in Command.objects.filter(pk__in=ids)}
    for comanda_id in dict.fromkeys(str(i) for i in ids):
        numero = conhecidas.get(comanda_id)
        if numero is None:
            resultado["skipped"].append({"id": comanda_id, "number": None, "reason": "Comanda não encontrada."})
            continue
        try:
            with transaction.atomic():
                retirados = _zerar_uma(
                    comanda_id, account=account, user=user, reason=reason,
                    authorized=authorized, authorized_by=authorized_by,
                )
        except (CancelamentoBloqueado, ValidationError) as exc:
            motivo = " ".join(getattr(exc, "messages", None) or [str(exc)])
            resultado["skipped"].append({"id": comanda_id, "number": numero, "reason": motivo})
            continue
        resultado["reset"].append({"id": comanda_id, "number": numero, "items_removed": retirados})
    return resultado


def _zerar_uma(comanda_id, *, account, user, reason, authorized, authorized_by):
    from apps.orders.command_billing import billable_items_of
    from apps.orders.command_item_void import void_command_item
    from apps.orders.command_items import free_command_if_empty
    from apps.orders.models import Order, OrderItem
    from apps.restaurants.models import Command

    with tenant_context(account):
        comanda = Command.objects.select_for_update().get(pk=comanda_id)
        abertos = list(billable_items_of([comanda.pk]))

        # O que já está numa conta aberta não se cancela por aqui: a conta
        # ficaria com um item que a comanda diz não existir. Releitura depois
        # da trava — conferir antes não impede outro caixa de anexar no meio.
        contas = sorted(
            OrderItem.objects.filter(
                command_item__in=abertos,
                order__deleted_at__isnull=True,
                order__status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
            ).values_list("order__sequence", flat=True).distinct()
        )
        if contas:
            onde = ", ".join(f"#{numero}" for numero in contas)
            raise ValidationError(
                f"Está na conta {onde}, que continua aberta. Conclua a conta ou retire o cartão dela antes."
            )

        for item in abertos:
            void_command_item(
                item, user=user, reason=reason, authorized=authorized,
                authorized_by=authorized_by, avisar_entregue=False,
            )
        free_command_if_empty(comanda, user=user)
        record_audit(
            action=AuditLog.ACTION_UPDATED, instance=comanda, actor=user, reason=reason,
            metadata={
                "event": "command_reset",
                "items_removed": len(abertos),
                **({"authorized_by": str(authorized_by.pk)} if authorized_by else {}),
            },
        )
        return len(abertos)
