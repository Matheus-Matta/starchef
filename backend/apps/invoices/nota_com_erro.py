"""A nota que falhou ANTES de ser montada também fica gravada, com o motivo.

Recusa da SEFAZ e cadastro incompleto já ficavam na nota. O que falhava antes
— pedido sem item faturável, CPF/CNPJ inválido, uma exceção no meio da
montagem — devolvia só um 400/500: a venda paga ficava sem nota e sem
registro de que deveria ter tido uma, e não havia o que reenviar depois de
corrigir.

A nota nasce SEM número e sem chave: o número só é gasto quando a montagem dá
certo (um buraco na série exigiria inutilização na SEFAZ). O reenvio de uma
nota assim passa pela emissão inteira (`emitir_de_novo`), que a reaproveita.
"""
from decimal import Decimal

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.invoices.models import Invoice

#: Falha de DADOS (do pedido ou do cliente): corrigir e reenviar resolve.
FALHA_ANTES_DA_MONTAGEM = "before_assembly"


def registrar(order, config, motivo, *, user=None):
    """Grava (ou atualiza) a nota do pedido em erro, sem número nem chave."""
    from apps.invoices.services import _mark_failed

    # Relida do banco: uma montagem que quebrou no meio deixou o objeto em
    # memória com número e chave que a transação desfez.
    invoice = Invoice.all_objects.filter(order=order).first() or Invoice(order=order)
    invoice.account = order.account
    invoice.restaurant = order.restaurant
    invoice.branch = config.branch
    invoice.phase = Invoice.PHASE_FISCAL
    invoice.provider = config.provider
    invoice.document_model = config.document_model
    invoice.environment = config.environment
    invoice.crt = config.crt
    invoice.emitter_cnpj = config.cnpj
    invoice.emitter_name = config.corporate_name or config.trade_name
    invoice.total_amount = order.total
    invoice.products_total = order.subtotal or Decimal("0")
    invoice.discount_total = order.discount + order.coupon_discount
    nova = invoice._state.adding
    if nova:
        invoice.created_by = user
    invoice.updated_by = user
    _mark_failed(invoice, FALHA_ANTES_DA_MONTAGEM, motivo)
    invoice.save()
    record_audit(
        action=AuditLog.ACTION_CREATED if nova else AuditLog.ACTION_UPDATED,
        instance=invoice,
        actor=user,
        metadata={"fiscal_failure": FALHA_ANTES_DA_MONTAGEM, "message": str(motivo)[:500]},
    )
    return invoice


def nunca_montada(invoice):
    """Sem número: falhou antes da montagem, e o reenvio é a emissão inteira."""
    return not (invoice.number or "").strip()


def emitir_de_novo(invoice, *, user=None):
    from apps.invoices.services import emit_fiscal_invoice

    return emit_fiscal_invoice(invoice.order, user=user)
