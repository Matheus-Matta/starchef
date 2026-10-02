"""A linha do tempo de uma comanda, montada do que já está gravado.

Não há tabela de eventos: cada fato já tem dono. O item guarda quem lançou
(e o código do operador), a produção, o cancelamento e o encerramento no
cartão; o pedido guarda a cobrança e o cancelamento da conta; o registro de
mesa guarda vínculos; a auditoria guarda o zeramento. Uma tabela à parte seria
uma cópia gravada em mais um lugar — e cópia diverge.

O período (`after`/`before`, datas) filtra pelos itens LANÇADOS nele e pelos
registros de mesa e zeramento feitos nele: um cartão reutilizável acumula
meses de histórico, e a tela pede uma janela.
"""
ROTULOS = {
    "launched": "Lançado",
    "sent_to_production": "Enviado para produção",
    "preparing": "Em preparo",
    "ready": "Pronto",
    "delivered": "Entregue",
    "voided": "Cancelado",
    "charged": "Cobrado na conta",
    "released": "Encerrado sem cobrança",
    "order_cancelled": "Conta cancelada",
    "reset": "Comanda zerada",
    "table_linked": "Vinculada à mesa",
    "table_unlinked": "Desvinculada da mesa",
    "table_transferred": "Transferida de mesa",
}


def _pessoa(usuario):
    if usuario is None:
        return ""
    return usuario.get_full_name() or usuario.get_username()


def _evento(kind, at, *, user=None, operator_code="", item=None, order=None, table=None, reason=""):
    return {
        "at": at.isoformat(),
        "kind": kind,
        "label": ROTULOS[kind],
        "user": _pessoa(user),
        "operator_code": operator_code,
        "item": item,
        "order": order,
        "table": table,
        "reason": reason or "",
    }


def montar_historico(comanda, *, after=None, before=None):
    """Eventos da comanda, do mais novo para o mais antigo."""
    from apps.core.models import AuditLog
    from apps.orders.models import CommandItem, Order, OrderItem
    from apps.orders.operator_code import codigo_de
    from apps.restaurants.models import CommandMovementLog

    itens = CommandItem.objects.filter(command=comanda).select_related("product", "launched_by", "voided_by", "table")
    mesas = CommandMovementLog.objects.filter(command=comanda).select_related("waiter", "table", "from_table")
    zeramentos = AuditLog.objects.filter(
        account_id=comanda.account_id, entity="Command", object_id=str(comanda.pk), metadata__event="command_reset"
    ).select_related("actor")
    if after:
        itens, mesas, zeramentos = (q.filter(**{campo: after}) for q, campo in (
            (itens, "launched_at__date__gte"), (mesas, "created_at__date__gte"), (zeramentos, "created_at__date__gte")))
    if before:
        itens, mesas, zeramentos = (q.filter(**{campo: before}) for q, campo in (
            (itens, "launched_at__date__lte"), (mesas, "created_at__date__lte"), (zeramentos, "created_at__date__lte")))

    itens = list(itens)
    pedido_do_item = {
        linha.command_item_id: linha.order
        for linha in OrderItem.all_objects.filter(command_item__in=itens).select_related("order", "order__cancelled_by")
    }
    eventos = []
    for item in itens:
        resumo = {"id": str(item.pk), "product": item.product.name, "quantity": str(item.quantity), "total": str(item.total_price)}
        pedido = pedido_do_item.get(item.pk)
        conta = {"id": str(pedido.pk), "sequence": pedido.sequence} if pedido else None
        mesa = str(item.table.number) if item.table_id else None
        eventos.append(_evento("launched", item.launched_at, user=item.launched_by,
                               operator_code=codigo_de(item.metafields), item=resumo, table=mesa))
        for kind, quando in (("sent_to_production", item.sent_to_kitchen_at), ("preparing", item.preparation_started_at),
                             ("ready", item.ready_at), ("delivered", item.delivered_at)):
            if quando:
                eventos.append(_evento(kind, quando, item=resumo))
        if item.voided_at:
            eventos.append(_evento("voided", item.voided_at, user=item.voided_by, item=resumo, reason=item.void_reason))
        if item.command_closed_at and item.command_status == CommandItem.STATUS_COBRADO:
            eventos.append(_evento("charged", item.command_closed_at, item=resumo, order=conta))
        elif item.command_closed_at and item.command_status == CommandItem.STATUS_CANCELADO and not item.voided_at:
            eventos.append(_evento("released", item.command_closed_at, item=resumo, order=conta))
        if pedido and pedido.status in (Order.STATUS_CANCELLED, Order.STATUS_REFUNDED) and pedido.cancelled_at:
            eventos.append(_evento("order_cancelled", pedido.cancelled_at, user=pedido.cancelled_by,
                                   item=resumo, order=conta, reason=pedido.cancel_reason))

    tipo_da_mesa = {
        CommandMovementLog.ACTION_LINKED: "table_linked",
        CommandMovementLog.ACTION_UNLINKED: "table_unlinked",
        CommandMovementLog.ACTION_TRANSFERRED: "table_transferred",
    }
    for registro in mesas:
        mesa = registro.table or registro.from_table
        eventos.append(_evento(tipo_da_mesa[registro.action], registro.created_at, user=registro.waiter,
                               table=str(mesa.number) if mesa else None))
    for registro in zeramentos:
        eventos.append(_evento("reset", registro.created_at, user=registro.actor, reason=registro.reason))

    # Desempate estável: dois fatos no mesmo instante saem na ordem em que
    # acontecem no ciclo (lançar antes de cancelar), lida de trás para frente.
    ordem = {kind: posicao for posicao, kind in enumerate(ROTULOS)}
    eventos.sort(key=lambda e: (e["at"], ordem[e["kind"]]), reverse=True)
    return eventos


def pagina_do_historico(request, comanda):
    """`?page`, `?page_size` (até 200) e `?after`/`?before` (AAAA-MM-DD)."""
    from django.utils.dateparse import parse_date
    from rest_framework.exceptions import ValidationError

    datas = {}
    for campo in ("after", "before"):
        bruto = request.query_params.get(campo)
        if bruto:
            datas[campo] = parse_date(bruto)
            if datas[campo] is None:
                raise ValidationError({campo: "Use o formato AAAA-MM-DD."})
    try:
        pagina = max(int(request.query_params.get("page") or 1), 1)
        tamanho = min(max(int(request.query_params.get("page_size") or 50), 1), 200)
    except ValueError as exc:
        raise ValidationError({"page": "Página e tamanho são números."}) from exc

    eventos = montar_historico(comanda, **datas)
    inicio = (pagina - 1) * tamanho

    def link(numero):
        consulta = request.query_params.copy()
        consulta["page"] = numero
        return request.build_absolute_uri(f"{request.path}?{consulta.urlencode()}")

    return {
        "count": len(eventos),
        "next": link(pagina + 1) if inicio + tamanho < len(eventos) else None,
        "previous": link(pagina - 1) if pagina > 1 else None,
        "results": eventos[inicio:inicio + tamanho],
    }
