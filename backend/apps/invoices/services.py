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


def _resolve_fiscal_config(restaurant, branch=None):
    """Acha a `FiscalConfig` ativa pra emissao.

    `Order.branch`/`Invoice.branch` ficam `None` hoje (a unificacao
    Restaurant<->Filial — STC-050 — ainda esta pendente; ver apps/orders/views.py
    e apps/orders/services.py, que tambem criam pedidos com `branch=None` de
    proposito). Enquanto isso nao muda, resolve por filial quando disponivel e
    cai para qualquer config ativa do restaurante — funciona hoje (sempre cai
    no fallback) e continua correto quando o pedido passar a ter filial.
    """
    if branch is not None:
        config = FiscalConfig.objects.filter(branch=branch, is_active=True).first()
        if config:
            return config
    return FiscalConfig.objects.filter(branch__restaurant=restaurant, is_active=True).first()


@transaction.atomic
def emit_fiscal_invoice(order, *, cpf=None, cpf_name="", user=None):
    """Emite (monta) o documento fiscal do pedido. Idempotente por pedido (OneToOne)."""
    with tenant_context(order.account):
        order = Order.objects.select_for_update().get(pk=order.pk)

        config = _resolve_fiscal_config(order.restaurant, order.branch)
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
        invoice.branch = config.branch  # a filial cuja FiscalConfig realmente emitiu a nota.
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
                branch=invoice.branch,
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
        # Um provider real pode falhar (rede fora, SEFAZ indisponivel): a venda ja
        # esta paga, entao a falha nao pode travar o fechamento. Cai em
        # contingencia (tpEmis=9) — a chave de acesso e refeita porque o tpEmis
        # faz parte dela, e o DANFE sai imprimivel com o aviso de contingencia.
        try:
            get_provider(config.provider).emit(invoice, config)
        except Exception as exc:  # noqa: BLE001 — qualquer falha do provider vira contingencia, nao 500.
            invoice.emission_type = Invoice.EMISSION_CONTINGENCY
            access_key, numeric_code = build_access_key(
                uf=config.uf,
                emission_date=emission_dt,
                cnpj=config.cnpj,
                model=config.document_model,
                series=config.series,
                number=number,
                emission_type=Invoice.EMISSION_CONTINGENCY,
            )
            invoice.access_key = access_key
            invoice.qr_code_data = build_nfce_qrcode(
                access_key=access_key,
                environment=config.environment,
                csc_id=config.csc_id,
                csc_token=config.csc_token,
                base_url=config.qr_base_url,
            )
            invoice.fiscal_payload["cNF"] = numeric_code
            invoice.status = Invoice.STATUS_PENDING
            invoice.error_message = str(exc)
        invoice.issued_at = emission_dt
        invoice.save()

        config.next_number = number + 1
        config.save(update_fields=["next_number", "updated_at"])

        record_audit(action=AuditLog.ACTION_CREATED, instance=invoice, actor=user, metadata={"access_key": access_key})
        return invoice


@transaction.atomic
def cancel_fiscal_invoice(invoice, reason="", user=None):
    with tenant_context(invoice.account):
        config = _resolve_fiscal_config(invoice.restaurant, invoice.branch)
        provider = get_provider(config.provider if config else None)
        provider.cancel(invoice, reason)
        invoice.updated_by = user
        invoice.save(update_fields=["status", "error_message", "updated_by", "updated_at"])
        record_audit(action=AuditLog.ACTION_CANCELLED, instance=invoice, actor=user, reason=reason)
        return invoice


def reprocess_pending_fiscal_invoices(*, account=None):
    """Tenta retransmitir notas em contingencia (tpEmis=9) cuja SEFAZ/provider
    real ficou indisponivel no momento da venda. Chamado por
    `manage.py reprocess_pending_invoices`, manualmente ou por agendamento
    futuro (Celery beat) — cada nota e independente, uma falha nao trava as
    demais. Devolve (retried, issued) para o comando reportar.

    Varre TODAS as contas (`all_objects`, nao o manager escopado por tenant):
    isso roda fora do ciclo de uma unica requisicao/conta, entao nao ha um
    tenant "atual" — cada nota e reprocessada dentro do proprio `tenant_context`.
    """
    queryset = Invoice.all_objects.filter(status=Invoice.STATUS_PENDING, emission_type=Invoice.EMISSION_CONTINGENCY)
    if account is not None:
        queryset = queryset.filter(account=account)

    retried = 0
    issued = 0
    for invoice in queryset.select_related("branch", "restaurant"):
        retried += 1
        with tenant_context(invoice.account):
            config = _resolve_fiscal_config(invoice.restaurant, invoice.branch)
            if not config:
                continue
            try:
                get_provider(config.provider).emit(invoice, config)
            except Exception as exc:  # noqa: BLE001 — continua em contingencia, tenta de novo na proxima chamada.
                invoice.error_message = str(exc)
                invoice.save(update_fields=["error_message", "updated_at"])
                continue
            invoice.save()
            if invoice.status == Invoice.STATUS_ISSUED:
                issued += 1
                record_audit(action=AuditLog.ACTION_UPDATED, instance=invoice, metadata={"reprocessed": True})
    return retried, issued


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


_DANFE_WIDTH = 48  # mesma largura (fonte A, bobina 80mm) usada pelos outros cupons.


def _danfe_linha_valor(rotulo, valor):
    quantia = f"R$ {valor}"
    largura_rotulo = _DANFE_WIDTH - 14
    rotulo = str(rotulo)[:largura_rotulo]
    return f"{rotulo:<{largura_rotulo}}{quantia:>14}"


def _danfe_nfce_text(invoice, config):
    """Renderiza o DANFE NFC-e em texto monoespaçado 48 colunas.

    Mesmo conteudo do template HTML (`danfe_nfce.html`) — necessario porque o
    agente local de impressao so consegue mandar bytes ESC/POS puros pra
    impressoras de rede/serial; so a via de spool do Windows renderiza HTML.
    """
    lines = ["=" * _DANFE_WIDTH]
    name = (config.corporate_name if config else "") or invoice.emitter_name or "RAZAO SOCIAL"
    lines.append(name.center(_DANFE_WIDTH)[:_DANFE_WIDTH])
    cnpj = invoice.emitter_cnpj or "__.___.___/____-__"
    ie = f" IE: {config.ie}" if config and config.ie else ""
    lines.append(f"CNPJ: {cnpj}{ie}".center(_DANFE_WIDTH)[:_DANFE_WIDTH])
    if config and config.address_line:
        address = f"{config.address_line}"
        if config.city:
            address += f" - {config.city}/{config.uf}"
        lines.append(address.center(_DANFE_WIDTH)[:_DANFE_WIDTH])
    lines.append("-" * _DANFE_WIDTH)
    lines.append("DANFE NFC-e".center(_DANFE_WIDTH))
    lines.append("Documento Auxiliar da NFC-e".center(_DANFE_WIDTH))
    if invoice.environment == FiscalConfig.ENV_HOMOLOGATION:
        lines.append("-" * _DANFE_WIDTH)
        lines.append("SEM VALOR FISCAL - HOMOLOGACAO".center(_DANFE_WIDTH))
    if invoice.emission_type == Invoice.EMISSION_CONTINGENCY:
        lines.append("-" * _DANFE_WIDTH)
        lines.append("EMITIDA EM CONTINGENCIA".center(_DANFE_WIDTH))
        lines.append("TRANSMITIR QUANDO A CONEXAO VOLTAR".center(_DANFE_WIDTH))
    lines.append("-" * _DANFE_WIDTH)

    for item in invoice.items.all():
        lines.append(
            _danfe_linha_valor(
                f"{item.line_number} {item.code or '-'} {item.description}",
                item.total_price,
            )
        )
        lines.append(f"  {item.quantity:.3f} {item.unit} x R$ {item.unit_price}"[:_DANFE_WIDTH])

    lines.append("-" * _DANFE_WIDTH)
    lines.append(_danfe_linha_valor("Valor dos produtos", invoice.products_total))
    if invoice.discount_total:
        lines.append(_danfe_linha_valor("Desconto", invoice.discount_total))
    lines.append(_danfe_linha_valor("VALOR A PAGAR R$", invoice.total_amount))
    lines.append(f"Tributos aprox. (Lei 12.741): R$ {invoice.tax_approx_total}"[:_DANFE_WIDTH])
    lines.append("-" * _DANFE_WIDTH)

    if invoice.recipient_cpf:
        lines.append(f"CONSUMIDOR - CPF: {invoice.recipient_cpf} {invoice.recipient_name}"[:_DANFE_WIDTH])
    else:
        lines.append("CONSUMIDOR NAO IDENTIFICADO")
    lines.append("-" * _DANFE_WIDTH)

    lines.append(f"NFC-e n. {invoice.number} Serie {invoice.series}"[:_DANFE_WIDTH])
    if invoice.issued_at:
        lines.append(f"Emissao: {timezone.localtime(invoice.issued_at):%d/%m/%Y %H:%M}")
    lines.append("Consulte pela Chave de Acesso em:".center(_DANFE_WIDTH))
    lines.append((config.portal_url if config and config.portal_url else "(portal da SEFAZ da UF)").center(_DANFE_WIDTH))
    lines.append(format_access_key(invoice.access_key).center(_DANFE_WIDTH))
    lines.append("-" * _DANFE_WIDTH)

    if invoice.authorization_protocol:
        lines.append("Protocolo de autorizacao:".center(_DANFE_WIDTH))
        lines.append(invoice.authorization_protocol.center(_DANFE_WIDTH))
        if invoice.authorized_at:
            lines.append(f"{timezone.localtime(invoice.authorized_at):%d/%m/%Y %H:%M:%S}".center(_DANFE_WIDTH))
    else:
        lines.append("AGUARDANDO AUTORIZACAO".center(_DANFE_WIDTH))
        lines.append("(protocolo sera preenchido apos transmissao)".center(_DANFE_WIDTH))
    lines.append("=" * _DANFE_WIDTH)
    return "\n".join(lines)


def print_fiscal_invoice(invoice, *, user=None, printer=None):
    """Renderiza o DANFE NFC-e e cria o PrintJob (reaproveita o pipeline de impressao)."""
    from apps.printers.models import PrintJob

    with tenant_context(invoice.account):
        config = _resolve_fiscal_config(invoice.restaurant, invoice.branch)
        is_contingency = invoice.emission_type == Invoice.EMISSION_CONTINGENCY
        context = {
            "invoice": invoice,
            "items": invoice.items.all(),
            "config": config,
            "qr_uri": _qr_data_uri(invoice.qr_code_data),
            "access_key_fmt": format_access_key(invoice.access_key),
            "is_homologation": invoice.environment == FiscalConfig.ENV_HOMOLOGATION,
            "is_contingency": is_contingency,
            "pending": invoice.status == Invoice.STATUS_PENDING,
        }
        html = render_to_string("printers/danfe_nfce.html", context)
        # payload_version 2 + qr_data: mesmo formato que o agente local (Flutter)
        # ja usa pra Code128 (ver apps/printers/services.py) — aqui e o QR Code
        # da NFC-e, obrigatorio no DANFE, pra impressoras de rede/serial que nao
        # renderizam o <img> do HTML (so a via de spool do Windows faz isso).
        job = PrintJob.objects.create(
            account=invoice.account,
            restaurant=invoice.restaurant,
            branch=invoice.branch,
            printer=printer,
            order=invoice.order,
            job_type=PrintJob.TYPE_FISCAL,
            status=PrintJob.STATUS_PENDING,
            payload={
                "payload_version": 2,
                "invoice_id": str(invoice.id),
                "access_key": invoice.access_key,
                "number": invoice.number,
                "text_content": _danfe_nfce_text(invoice, config),
                "qr_data": invoice.qr_code_data,
            },
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        record_audit(action=AuditLog.ACTION_PRINTED, instance=job, actor=user, metadata={"job_type": PrintJob.TYPE_FISCAL})
        return job
