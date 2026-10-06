"""O comprovante do pedido CANCELADO.

Separado de `services.py` porque é um documento com conteúdo próprio: o que
foi desfeito, por quê, quem pediu e quem autorizou. O recibo de venda mostra o
que foi cobrado; este mostra que a cobrança deixou de valer.
"""
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.orders.models import OrderItem
from apps.printers.models import PrintJob
from apps.printers.services import (
    LARGURA_CUPOM,
    _establishment_info,
    _linha_valor,
    _order_context_lines,
    printer_payload,
    resolve_printer_for,
)


def _nome(usuario):
    if usuario is None:
        return ""
    return usuario.get_full_name() or usuario.get_username()


def cancellation_receipt_text(order):
    info = _establishment_info(order)
    linha = "-" * LARGURA_CUPOM
    lines = [
        info["trade_name"].upper().center(LARGURA_CUPOM),
        "COMPROVANTE DE CANCELAMENTO".center(LARGURA_CUPOM),
        "NAO E DOCUMENTO FISCAL".center(LARGURA_CUPOM),
        linha,
        f"Pedido nº {order.sequence}",
        *_order_context_lines(order),
        f"Aberto em: {timezone.localtime(order.opened_at):%d/%m/%Y %H:%M}",
    ]
    if order.cancelled_at:
        lines.append(f"Cancelado em: {timezone.localtime(order.cancelled_at):%d/%m/%Y %H:%M}")
    lines.append(linha)
    # Os itens estão todos cancelados agora: o comprovante mostra o que a
    # venda TINHA. Cortesia nunca foi cobrada, então não entra.
    for item in order.items.select_related("product").exclude(status=OrderItem.STATUS_COMPED):
        descricao = f"{item.quantity:g} x {item.product.name}{item.variation_suffix}"
        lines.append(_linha_valor(descricao, item.total_price))
    lines.extend([linha, _linha_valor("TOTAL CANCELADO", order.total)])
    estornos = order.payments.select_related("payment_method").order_by("created_at")
    if estornos.exists():
        lines.extend([linha, "RECEBIMENTOS DESFEITOS"])
        for pagamento in estornos:
            lines.append(_linha_valor(pagamento.payment_method.name, pagamento.amount))
    lines.extend([linha, f"Motivo: {order.cancel_reason}"[:LARGURA_CUPOM]])
    if order.cancelled_by_id:
        lines.append(f"Cancelado por: {_nome(order.cancelled_by)}"[:LARGURA_CUPOM])
    if order.cancel_authorized_by_id:
        lines.append(f"Autorizado por: {_nome(order.cancel_authorized_by)}"[:LARGURA_CUPOM])
    elif order.cancel_authorization:
        lines.append(f"Autorização: {order.get_cancel_authorization_display()}"[:LARGURA_CUPOM])
    lines.extend([linha, ""])
    return "\n".join(lines)


def register_cancellation_receipt(*, order, user, printer=None, terminal_prints=True):
    """Cria o job do comprovante.

    `terminal_prints=True`: o terminal que pediu imprime (e o agente pula o
    job). `False`: ninguém do outro lado imprime — painel web, app —, então o
    job vai para a fila automática do agente da loja.
    """
    with tenant_context(order.account):
        if printer is None:
            printer = resolve_printer_for(order, PrintJob.TYPE_RECEIPT)
        texto = cancellation_receipt_text(order)
        job = PrintJob.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            printer=printer,
            order=order,
            job_type=PrintJob.TYPE_ORDER_CANCEL,
            status=PrintJob.STATUS_RENDERED,
            payload={
                "account_id": str(order.account_id),
                "order_id": str(order.id),
                "sequence": order.sequence,
                "manual_only": terminal_prints,
                "text_content": texto,
            },
            html_content=f"<pre>{texto}</pre>",
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        record_audit(
            action=AuditLog.ACTION_PRINTED, instance=job, actor=user,
            metadata={"job_type": PrintJob.TYPE_ORDER_CANCEL},
        )
        return job


def cancellation_print_response(*, order, user, terminal_prints=True):
    """O que a resposta do `/cancel/` leva: o job para o terminal imprimir.

    Sem terminal que imprima, o job vai para a fila do agente e a resposta
    não o devolve — senão um cliente antigo imprimiria a segunda via.

    A falta de impressora vira `cancellation_print_error`, nunca erro da
    requisição: o cancelamento JÁ valeu, e um 400 faria o PDV ler "não
    cancelou" num pedido cancelado.
    """
    try:
        job = register_cancellation_receipt(order=order, user=user, terminal_prints=terminal_prints)
    except ValidationError as exc:
        return {"cancellation_print_error": " ".join(exc.messages)}
    if not terminal_prints:
        return {}
    return {
        "cancellation_print": {
            "print_job_id": str(job.id),
            "payload": job.payload,
            "status": job.status,
            "printer": printer_payload(job.printer),
        }
    }
