"""Aprovação do desconto manual do pedido — e o registro de quem aprovou.

O caixa digita o desconto no PDV; quem APROVA é um gerente: o próprio
operador, se tiver o cargo, ou alguém que libere ali, no mesmo request, com a
senha de ações do caixa ou o login de quem tem `cash.approve`. A aprovação fica
no pedido (quem, como, quando) e na auditoria (de quanto para quanto).

Só o desconto que MUDA pede aprovação. Fechar de novo para corrigir a taxa não
pode pedir a senha outra vez para o mesmo valor já liberado.
"""
from rest_framework.exceptions import PermissionDenied

from apps.core.access import has_role_at_least
from apps.core.audit import record_audit
from apps.core.models import AuditLog

#: A permissão de quem libera por login (ver `permission_catalog`).
PERMISSAO = "cash.approve"


class DescontoSemAprovacao(PermissionDenied):
    default_detail = (
        "O desconto precisa da aprovação de um gerente: informe a senha de "
        "ações do caixa."
    )
    default_code = "discount_authorization_required"


def aprovar(order, desconto, *, user, autorizar, agora):
    """Confere e registra a aprovação ANTES de gravar `desconto` no pedido.

    `order` já vem travado e relido. `autorizar()` devolve
    `(aprovado, quem, como)` e só é chamada quando precisa — a senha não é
    conferida à toa.
    """
    from apps.orders.models import Order

    anterior = order.discount
    if desconto <= 0:
        order.discount_authorized_by = None
        order.discount_authorization = ""
        order.discount_authorized_at = None
        return
    if desconto == anterior:
        # Valor já gravado (inclusive o de antes desta regra, sem registro):
        # não há desconto NOVO a aprovar.
        return
    if has_role_at_least(user, "manager"):
        aprovado, quem, como = True, user, Order.AUTHORIZATION_OWN
    else:
        aprovado, quem, como = autorizar() if autorizar else (False, None, "")
    if not aprovado:
        raise DescontoSemAprovacao()
    order.discount_authorized_by = quem
    order.discount_authorization = como
    order.discount_authorized_at = agora
    record_audit(
        action=AuditLog.ACTION_UPDATED,
        instance=order,
        actor=user,
        metadata={
            "event": "order_discount_approved",
            "from": str(anterior),
            "to": str(desconto),
            "authorization": como,
            "authorized_by": str(getattr(quem, "id", "") or ""),
        },
    )
