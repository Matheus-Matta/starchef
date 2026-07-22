from decimal import Decimal

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.printers.models import PrintJob

# Mapa explicito job_type -> template. Evita heuristica fragil por substring
# (weigh_ticket e kitchen_ticket ambos contem "ticket").
_TEMPLATE_BY_TYPE = {
    PrintJob.TYPE_KITCHEN: "printers/kitchen_ticket.html",
    PrintJob.TYPE_BAR: "printers/kitchen_ticket.html",
    PrintJob.TYPE_WEIGH: "printers/weigh_ticket.html",
    PrintJob.TYPE_RECEIPT: "printers/receipt.html",
    PrintJob.TYPE_PAYMENT: "printers/receipt.html",
    PrintJob.TYPE_TABLE_BILL: "printers/receipt.html",
    PrintJob.TYPE_CASH_CLOSE: "printers/receipt.html",
}
_WITH_PAYMENTS = {PrintJob.TYPE_PAYMENT, PrintJob.TYPE_RECEIPT}


def render_print_html(order, job_type, **extra):
    """Renderiza o HTML de um job a partir do template correspondente ao tipo."""
    template = _TEMPLATE_BY_TYPE.get(job_type, "printers/receipt.html")
    context = {"order": order, "items": order.items.select_related("product").all(), **extra}
    if job_type in _WITH_PAYMENTS:
        context["payments"] = order.payments.select_related("payment_method").order_by("created_at")
    return render_to_string(template, context)


def register_print_job(*, order, user, job_type=PrintJob.TYPE_RECEIPT, printer=None):
    with tenant_context(order.account):
        if printer and printer.account_id != order.account_id:
            raise ValueError("Printer does not belong to the order account.")

        html = render_print_html(order, job_type)
        job = PrintJob.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            printer=printer,
            order=order,
            job_type=job_type,
            status=PrintJob.STATUS_RENDERED,
            payload={"account_id": str(order.account_id), "order_id": str(order.id), "sequence": order.sequence},
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        record_audit(action=AuditLog.ACTION_PRINTED, instance=job, actor=user, metadata={"job_type": job_type})
        return job


# ── Nota de pesagem (balanca por kilo) ─────────────────────────────────────
def _weigh_ticket_text(order, item, scale):
    """Versao texto (monospace) da nota, enviada pelo agente para impressoras ESC/POS."""
    restaurant = order.restaurant.trade_name if order.restaurant_id else "Restaurante"
    where = f"Mesa {order.table.number}" if order.table_id else (f"Comanda {order.command.code}" if order.command_id else "Balcao")
    lines = [
        restaurant.center(32),
        "NOTA DE PESAGEM".center(32),
        "-" * 32,
        f"Pedido #{order.sequence}  {where}",
        timezone.localtime(item.created_at).strftime("%d/%m/%Y %H:%M"),
        "-" * 32,
        item.product.name[:32],
        f"{Decimal(item.quantity):.3f} kg x R$ {item.unit_price}/kg",
        f"{'VALOR'.ljust(20)}{('R$ ' + str(item.total_price)).rjust(12)}",
        "-" * 32,
        f"{'TOTAL DO PEDIDO'.ljust(18)}{('R$ ' + str(order.total)).rjust(14)}",
        "",
        "Pague no caixa. Obrigado!".center(32),
    ]
    return "\n".join(lines)


def register_weigh_print(*, order, item, scale, user=None):
    """Gera a nota de pesagem (HTML + texto) como PrintJob PENDENTE na impressora da balanca.

    Fica pendente ate o agente local imprimir e chamar mark-printed. Sem impressora
    configurada, ainda registra o job (util para reimpressao/navegador).
    """
    with tenant_context(order.account):
        printer = scale.printer if scale and scale.printer_id else None
        html = render_print_html(order, PrintJob.TYPE_WEIGH, item=item, scale=scale)
        job = PrintJob.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            printer=printer,
            order=order,
            job_type=PrintJob.TYPE_WEIGH,
            status=PrintJob.STATUS_PENDING,
            payload={
                "order_id": str(order.id),
                "item_id": str(item.id),
                "sequence": order.sequence,
                "weight_kg": str(item.quantity),
                "unit_price": str(item.unit_price),
                "total": str(item.total_price),
                # Texto pronto para a impressora termica (agente imprime este campo).
                "text_content": _weigh_ticket_text(order, item, scale),
            },
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        record_audit(action=AuditLog.ACTION_PRINTED, instance=job, actor=user, metadata={"job_type": PrintJob.TYPE_WEIGH})
        return job


def weigh_to_order(*, scale, order, user, scale_reading=None, weight_kg=None, do_print=True):
    """Fluxo principal: pesa -> lanca item por kg no pedido -> gera a nota de pesagem.

    Retorna (item, print_job). `print_job` e None quando `do_print=False`.
    """
    # Import tardio evita ciclo entre apps.orders.services e apps.printers.services.
    from apps.orders.services import add_order_item

    if not scale.product_id:
        raise ValidationError("Balanca sem produto por kilo configurado.")
    if order.account_id != scale.account_id:
        raise ValidationError("Pedido e balanca pertencem a contas diferentes.")

    item = add_order_item(
        order=order,
        product=scale.product,
        user=user,
        scale_reading=scale_reading,
        weight_kg=weight_kg,
    )
    job = register_weigh_print(order=order, item=item, scale=scale, user=user) if do_print else None
    return item, job
