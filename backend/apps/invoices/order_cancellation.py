from apps.invoices.models import Invoice


def cancel_invoice_for_order(order, *, reason, user):
    """Cancela junto a nota vinculada, se o pedido já tiver uma."""
    invoice = Invoice.all_objects.filter(order_id=order.pk).first()
    if invoice is None:
        return None

    from apps.invoices.services import cancel_fiscal_invoice

    return cancel_fiscal_invoice(invoice, reason=reason, user=user)
