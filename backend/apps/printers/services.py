from decimal import Decimal

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.printers.models import Printer, PrintJob

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


def _customer_receipt_text(order):
    restaurant = order.restaurant
    lines = [
        restaurant.trade_name.center(32),
        f"CNPJ: {restaurant.cnpj or '-'}",
        f"{restaurant.address or ''} {restaurant.city or ''} {restaurant.state or ''}".strip()[:32],
        "-" * 32,
        f"PEDIDO #{order.sequence}",
        f"Data: {timezone.localtime(order.opened_at):%d/%m/%Y %H:%M}",
    ]
    if order.table_id:
        lines.append(f"Mesa: {order.table.number}")
    if order.command_id:
        lines.append(f"Comanda: {order.command.code}")
    if order.customer_id:
        lines.append(f"Cliente: {order.customer.name}"[:32])
        if order.customer.phone:
            lines.append(f"Telefone: {order.customer.phone}"[:32])
    if order.responsible_user_id:
        operator = order.responsible_user.get_full_name() or order.responsible_user.username
        lines.append(f"Operador: {operator}"[:32])
    lines.append("-" * 32)
    for item in order.items.select_related("product").prefetch_related("addons__addon"):
        if item.status == item.STATUS_CANCELLED:
            continue
        lines.append(f"{item.quantity:g}x {item.product.name}"[:32])
        if item.product.is_weighed:
            lines.append(f"  {item.quantity:.3f} kg x R$ {item.unit_price}/kg"[:32])
        for variation in item.variations or []:
            name = variation.get("name", variation) if isinstance(variation, dict) else variation
            lines.append(f"  VAR: {name}"[:32])
        for addon in item.addons.all():
            lines.append(f"  + {addon.quantity:g}x {addon.addon.name}"[:32])
        if item.customer_note:
            lines.append(f"  OBS: {item.customer_note}"[:32])
        lines.append(f"{'':20}R$ {item.total_price:>8}")
    lines.extend(
        [
            "-" * 32,
            f"{'Subtotal':20}R$ {order.subtotal:>8}",
            f"{'Servico':20}R$ {order.service_fee:>8}",
            f"{'Desconto':20}R$ {order.discount:>8}",
            f"{'Entrega':20}R$ {order.delivery_fee:>8}",
            f"{'TOTAL':20}R$ {order.total:>8}",
        ]
    )
    payments = order.payments.select_related("payment_method").order_by("created_at")
    if payments.exists():
        lines.extend(["-" * 32, "PAGAMENTOS"])
        for payment in payments:
            lines.append(f"{payment.payment_method.name[:20]:20}R$ {payment.amount:>8}")
            if payment.change_amount:
                received = payment.metadata.get("received_amount", payment.amount)
                lines.append(f"{'Recebido':20}R$ {received:>8}")
                lines.append(f"{'Troco':20}R$ {payment.change_amount:>8}")
    if order.general_notes:
        lines.extend(["-" * 32, f"OBS: {order.general_notes}"[:32]])
    lines.extend(["-" * 32, "Obrigado pela preferencia!".center(32), ""])
    return "\n".join(lines)


def render_print_html(order, job_type, **extra):
    """Renderiza o HTML de um job a partir do template correspondente ao tipo."""
    template = _TEMPLATE_BY_TYPE.get(job_type, "printers/receipt.html")
    context = {"order": order, "items": order.items.select_related("product").all(), **extra}
    if job_type in _WITH_PAYMENTS:
        context["payments"] = order.payments.select_related("payment_method").order_by("created_at")
    return render_to_string(template, context)


def register_print_job(
    *,
    order,
    user,
    job_type=PrintJob.TYPE_RECEIPT,
    printer=None,
    manual_only=False,
):
    with tenant_context(order.account):
        if printer and printer.account_id != order.account_id:
            raise ValueError("Printer does not belong to the order account.")
        if printer is None:
            active = Printer.objects.filter(restaurant=order.restaurant, is_active=True)
            if job_type in {PrintJob.TYPE_KITCHEN, PrintJob.TYPE_BAR}:
                sector_ids = order.items.exclude(product__sector=None).values_list("product__sector_id", flat=True)
                printer = active.filter(sector_id__in=sector_ids).order_by("name").first()
            printer = printer or active.filter(sector=None).order_by("name").first() or active.order_by("name").first()

        html = render_print_html(order, job_type)
        job = PrintJob.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            printer=printer,
            order=order,
            job_type=job_type,
            status=PrintJob.STATUS_RENDERED,
            payload={
                "account_id": str(order.account_id),
                "order_id": str(order.id),
                "sequence": order.sequence,
                "manual_only": manual_only,
                "text_content": (
                    _customer_receipt_text(order)
                    if job_type in _WITH_PAYMENTS | {PrintJob.TYPE_TABLE_BILL}
                    else ""
                ),
            },
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        record_audit(action=AuditLog.ACTION_PRINTED, instance=job, actor=user, metadata={"job_type": job_type})
        return job


def _kitchen_ticket_text(*, order, batch, sector, items):
    where = (
        f"Mesa {order.table.number}"
        if order.table_id
        else (
            f"Comanda {order.command.code}"
            if order.command_id
            else order.get_order_type_display()
        )
    )
    lines = [
        str(sector.name).upper().center(32),
        f"PEDIDO #{order.sequence}".center(32),
        f"RODADA #{batch.batch_number}".center(32),
        "-" * 32,
        where,
        timezone.localtime(batch.sent_at).strftime("%d/%m/%Y %H:%M:%S"),
        "-" * 32,
    ]
    for item in items:
        lines.append(f"{item.quantity:g}x {item.product.name}"[:32])
        for variation in item.variations or []:
            name = variation.get("name", variation) if isinstance(variation, dict) else variation
            lines.append(f"  VAR: {name}"[:32])
        for addon in item.addons.all():
            lines.append(f"  + {addon.quantity:g}x {addon.addon.name}"[:32])
        if item.customer_note:
            lines.append(f"  OBS: {item.customer_note}"[:32])
        lines.append("-" * 32)
    lines.extend(["", "FIM DA RODADA".center(32), ""])
    return "\n".join(lines)


def register_kitchen_batch_print_jobs(*, batch, user):
    """Cria um ticket por impressora/setor contendo apenas os itens da rodada."""
    order = batch.order
    with tenant_context(order.account):
        items = list(
            batch.items.select_related("product__sector")
            .prefetch_related("addons__addon")
            .order_by("launched_at")
        )
        by_sector = {}
        for item in items:
            sector = item.product.sector
            if sector is not None:
                by_sector.setdefault(sector.id, {"sector": sector, "items": []})[
                    "items"
                ].append(item)

        jobs = []
        for group in by_sector.values():
            sector = group["sector"]
            sector_items = group["items"]
            printers = Printer.objects.filter(
                restaurant=order.restaurant,
                sector=sector,
                is_active=True,
            ).order_by("name")
            for printer in printers:
                html = render_print_html(
                    order,
                    PrintJob.TYPE_KITCHEN,
                    items=sector_items,
                    batch=batch,
                    sector=sector,
                )
                text = _kitchen_ticket_text(
                    order=order,
                    batch=batch,
                    sector=sector,
                    items=sector_items,
                )
                job = PrintJob.objects.create(
                    account=order.account,
                    restaurant=order.restaurant,
                    branch=order.branch,
                    printer=printer,
                    order=order,
                    job_type=PrintJob.TYPE_KITCHEN,
                    status=PrintJob.STATUS_RENDERED,
                    payload={
                        "account_id": str(order.account_id),
                        "order_id": str(order.id),
                        "sequence": order.sequence,
                        "batch_id": str(batch.id),
                        "batch_number": batch.batch_number,
                        "sector_id": str(sector.id),
                        "sector_name": sector.name,
                        "item_ids": [str(item.id) for item in sector_items],
                        "text_content": text,
                    },
                    html_content=html,
                    printed_by=user,
                    created_by=user,
                    updated_by=user,
                )
                jobs.append(job)
                record_audit(
                    action=AuditLog.ACTION_PRINTED,
                    instance=job,
                    actor=user,
                    metadata={
                        "job_type": PrintJob.TYPE_KITCHEN,
                        "batch": batch.batch_number,
                        "sector": str(sector.id),
                    },
                )
        return jobs


def register_printer_test_job(*, printer, user):
    """Gera uma nota de teste sem dispará-la automaticamente."""
    with tenant_context(printer.account):
        hidden_terms = ("password", "secret", "token", "senha", "chave")
        safe_settings = {
            key: value
            for key, value in (printer.settings or {}).items()
            if not any(term in str(key).lower() for term in hidden_terms)
        }
        sector = printer.sector.name if printer.sector_id else "Todos os setores"
        mode = "Ativada" if printer.auto_print else "Desativada"
        active = "Ativa" if printer.is_active else "Inativa"
        lines = [
            "STARCHEF PDV".center(32),
            "TESTE DE IMPRESSORA".center(32),
            "-" * 32,
            f"Nome: {printer.name}",
            f"Driver: {printer.get_driver_type_display()}",
            f"Conexao: {printer.get_connection_type_display()}",
            f"Windows/Serial: {printer.endpoint or 'Nao configurado'}",
            f"IP: {printer.host or 'Nao configurado'}",
            f"Porta TCP: {printer.port}",
            f"Timeout: {printer.timeout_seconds}s",
            f"Setor: {sector}",
            f"Impressao automatica: {mode}",
            f"Status: {active}",
            f"Executor: {safe_settings.get('executor', 'Nao informado')}",
        ]
        for key, value in sorted(safe_settings.items()):
            if key != "executor":
                lines.append(f"{key}: {value}")
        lines.extend(
            [
                "-" * 32,
                timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"),
                "CONEXAO REALIZADA".center(32),
                "",
            ]
        )
        text = "\n".join(lines)
        html = f"<pre>{text}</pre>"
        job = PrintJob.objects.create(
            account=printer.account,
            restaurant=printer.restaurant,
            branch=printer.branch,
            printer=printer,
            job_type="printer_test",
            status=PrintJob.STATUS_RENDERED,
            payload={"text_content": text, "diagnostic": True},
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
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
