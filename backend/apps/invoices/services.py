"""
Servicos fiscais: emissao do documento a partir de um pedido e impressao do DANFE.

Monta toda a parte deterministica (numero, chave de acesso, QR, tributos, itens)
e delega a etapa externa (autorizacao SEFAZ) ao provider configurado — que no
scaffold e o ManualFiscalProvider (deixa a nota `pending`, sem protocolo).
"""
import base64
import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.invoices.fiscal import (
    build_access_key,
    build_nfce_qrcode,
    compute_item_taxes,
    format_access_key,
    only_digits,
)
from apps.invoices.models import FiscalConfig, Invoice, InvoiceItem
from apps.invoices.providers import get_provider
from apps.orders.models import Order, OrderItem


@transaction.atomic
def emit_fiscal_invoice(order, *, cpf=None, cpf_name="", user=None):
    """Emite (monta) o documento fiscal do pedido. Idempotente por pedido (OneToOne)."""
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)

        config = FiscalConfig.objects.filter(branch=order.branch, is_active=True).first()
        if not config:
            raise ValidationError("Filial sem configuracao fiscal. Configure em Fiscal > Configuracao.")

        existing = getattr(order, "invoice", None)
        if existing and existing.status in (Invoice.STATUS_PENDING, Invoice.STATUS_ISSUED):
            raise ValidationError("Pedido ja possui nota fiscal emitida.")

        items = list(
            order.items.exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED]).select_related("product")
        )
        if not items:
            raise ValidationError("Pedido sem itens faturaveis.")

        number = config.next_number
        emission_dt = timezone.now()
        access_key, numeric_code = build_access_key(
            uf=config.uf,
            emission_date=emission_dt,
            cnpj=config.cnpj,
            model=config.document_model,
            series=config.series,
            number=number,
        )
        qr_data = build_nfce_qrcode(
            access_key=access_key,
            environment=config.environment,
            csc_id=config.csc_id,
            csc_token=config.csc_token,
            base_url=config.qr_base_url,
        )

        invoice = existing or Invoice(order=order)
        invoice.account = order.account
        invoice.restaurant = order.restaurant
        invoice.branch = order.branch
        invoice.phase = Invoice.PHASE_FISCAL
        invoice.document_model = config.document_model
        invoice.series = config.series
        invoice.number = str(number)
        invoice.environment = config.environment
        invoice.crt = config.crt
        invoice.access_key = access_key
        invoice.emitter_cnpj = config.cnpj
        invoice.emitter_name = config.corporate_name or config.trade_name
        invoice.recipient_cpf = only_digits(cpf) if cpf else ""
        invoice.recipient_name = cpf_name or ""
        invoice.qr_code_data = qr_data
        invoice.consult_url = config.portal_url
        invoice.created_by = getattr(invoice, "created_by", None) or user
        invoice.updated_by = user
        invoice.save()  # precisa de pk para os itens

        # (Re)monta os itens fiscais com o detalhamento tributario.
        invoice.items.all().delete()
        products_total = Decimal("0")
        approx_total = Decimal("0")
        for line, order_item in enumerate(items, start=1):
            profile = order_item.product.fiscal_profile or config.default_profile
            taxes = compute_item_taxes(total_price=order_item.total_price, profile=profile)
            unit = "KG" if getattr(order_item.product, "is_weighed", False) else "UN"
            InvoiceItem.objects.create(
                account=order.account,
                restaurant=order.restaurant,
                branch=order.branch,
                invoice=invoice,
                product=order_item.product,
                line_number=line,
                code=order_item.product.internal_code,
                description=order_item.product.name,
                ncm=(profile.ncm if profile else ""),
                cfop=(profile.cfop if profile else ""),
                csosn=(profile.csosn if profile else ""),
                cst_icms=(profile.cst_icms if profile else ""),
                origem=(profile.origem if profile else "0"),
                unit=unit,
                quantity=order_item.quantity,
                unit_price=order_item.unit_price,
                total_price=order_item.total_price,
                created_by=user,
                updated_by=user,
                **taxes,
            )
            products_total += order_item.total_price
            approx_total += taxes["approx_tax_value"]

        invoice.products_total = products_total
        invoice.discount_total = order.discount
        invoice.tax_approx_total = approx_total
        invoice.total_amount = order.total
        invoice.fiscal_payload = {"cNF": numeric_code, "emission": emission_dt.isoformat()}

        # Parte externa (autorizacao SEFAZ) — no manual, fica em branco/pending.
        get_provider(config.provider).emit(invoice, config)
        invoice.issued_at = emission_dt
        invoice.save()

        config.next_number = number + 1
        config.save(update_fields=["next_number", "updated_at"])

        record_audit(action=AuditLog.ACTION_CREATED, instance=invoice, actor=user, metadata={"access_key": access_key})
        return invoice


@transaction.atomic
def cancel_fiscal_invoice(invoice, reason="", user=None):
    with tenant_context(invoice.account):
        config = FiscalConfig.objects.filter(branch=invoice.branch).first()
        provider = get_provider(config.provider if config else None)
        provider.cancel(invoice, reason)
        invoice.updated_by = user
        invoice.save(update_fields=["status", "error_message", "updated_by", "updated_at"])
        record_audit(action=AuditLog.ACTION_CANCELLED, instance=invoice, actor=user, reason=reason)
        return invoice


def _qr_data_uri(data):
    """Gera o QR Code como PNG data-URI para embutir no cupom. Vazio se sem dado/lib."""
    if not data:
        return ""
    try:
        import qrcode

        buffer = io.BytesIO()
        qrcode.make(data).save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return ""


def print_fiscal_invoice(invoice, *, user=None, printer=None):
    """Renderiza o DANFE NFC-e e cria o PrintJob (reaproveita o pipeline de impressao)."""
    from apps.printers.models import PrintJob

    with tenant_context(invoice.account):
        config = FiscalConfig.objects.filter(branch=invoice.branch).first()
        context = {
            "invoice": invoice,
            "items": invoice.items.all(),
            "config": config,
            "qr_uri": _qr_data_uri(invoice.qr_code_data),
            "access_key_fmt": format_access_key(invoice.access_key),
            "is_homologation": invoice.environment == FiscalConfig.ENV_HOMOLOGATION,
            "pending": invoice.status == Invoice.STATUS_PENDING,
        }
        html = render_to_string("printers/danfe_nfce.html", context)
        job = PrintJob.objects.create(
            account=invoice.account,
            restaurant=invoice.restaurant,
            branch=invoice.branch,
            printer=printer,
            order=invoice.order,
            job_type=PrintJob.TYPE_FISCAL,
            status=PrintJob.STATUS_PENDING,
            payload={"invoice_id": str(invoice.id), "access_key": invoice.access_key, "number": invoice.number},
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        record_audit(action=AuditLog.ACTION_PRINTED, instance=job, actor=user, metadata={"job_type": PrintJob.TYPE_FISCAL})
        return job
