"""
Servicos fiscais: emissao do documento a partir de um pedido e impressao do DANFE.

Monta toda a parte deterministica (numero, chave de acesso, QR, tributos, itens)
e delega a etapa externa (autorizacao SEFAZ) ao provider configurado — que no
scaffold e o ManualFiscalProvider (deixa a nota `pending`, sem protocolo).
"""
import base64
import io
import logging
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
from apps.invoices.providers import fiscal_provider_unavailable_reason, get_provider
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


# Campos do emitente que nascem espelhados do cadastro do restaurante. Depois
# que a configuracao existe, quem manda neles e a pagina fiscal avancada
# (Restaurantes > acoes > Configuracao fiscal / Focus NFe): salvar o cadastro
# do restaurante so preenche o que ainda estiver em branco, senao trocar um
# telefone la apagaria a razao social fiscal ajustada aqui.
_EMITTER_FIELDS_FROM_RESTAURANT = {
    "cnpj": lambda restaurant: restaurant.cnpj or "",
    "ie": lambda restaurant: restaurant.state_registration or "",
    "corporate_name": lambda restaurant: restaurant.legal_name or "",
    "trade_name": lambda restaurant: restaurant.trade_name or "",
    "address_line": lambda restaurant: restaurant.address or "",
    "city": lambda restaurant: restaurant.city or "",
    "uf": lambda restaurant: restaurant.state or "",
    "zip_code": lambda restaurant: restaurant.zip_code or "",
}


def restaurant_fiscal_branch(restaurant):
    """A filial que sustenta a configuracao fiscal deste restaurante.

    `all_objects` de proposito: o signal `sync_branch_for_restaurant` tambem usa,
    e assim a filial e encontrada mesmo fora de um request com conta no contexto
    (tarefas Celery, comandos de manage.py).
    """
    from apps.restaurants.models import Branch

    return Branch.all_objects.filter(restaurant=restaurant).order_by("created_at").first()


def ensure_fiscal_config(restaurant, *, user=None, provider=None, overwrite=False):
    """Devolve (criando se preciso) a unica `FiscalConfig` da filial do restaurante.

    Ponto unico de criacao: antes o cadastro do restaurante e a tela fiscal
    criavam cada um a sua, e a segunda batia na `unique_fiscal_config_by_branch`
    virando um 409 "Ja existe um registro com estes dados" que travava o
    salvamento do restaurante. `all_objects` aqui tambem recupera uma config
    soft-deleted (a constraint e do banco e nao enxerga `deleted_at`).
    """
    branch = restaurant_fiscal_branch(restaurant)
    if branch is None:
        return None

    config = FiscalConfig.all_objects.filter(branch=branch).first()
    if config is None:
        config = FiscalConfig(
            account=restaurant.account,
            restaurant=restaurant,
            branch=branch,
            provider=provider or FiscalConfig.PROVIDER_MANUAL,
            created_by=user,
            updated_by=user,
            **{field: resolve(restaurant) for field, resolve in _EMITTER_FIELDS_FROM_RESTAURANT.items()},
        )
        config.save()
        return config

    changed = []
    if config.deleted_at is not None:
        config.deleted_at = None
        changed.append("deleted_at")
    if config.restaurant_id != restaurant.pk:
        config.restaurant = restaurant
        changed.append("restaurant")
    if provider is not None and config.provider != provider:
        config.provider = provider
        changed.append("provider")
    for field, resolve in _EMITTER_FIELDS_FROM_RESTAURANT.items():
        value = resolve(restaurant)
        if not value:
            continue
        if overwrite or not getattr(config, field):
            if getattr(config, field) != value:
                setattr(config, field, value)
                changed.append(field)
    if changed:
        if user is not None:
            config.updated_by = user
            changed.append("updated_by")
        config.save(update_fields=[*changed, "updated_at"])
    return config


def fiscal_emission_unavailable_reason(order):
    """Explica por que a API nao deve tentar transmitir uma nota deste pedido."""

    with tenant_context(order.account):
        config = _resolve_fiscal_config(order.restaurant, order.branch)
        if config is None:
            return "O restaurante nao possui configuracao fiscal ativa."
        return fiscal_provider_unavailable_reason(config)


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
                cest=(profile.cest if profile else ""),
                cfop=(profile.cfop if profile else ""),
                csosn=(profile.csosn if profile else ""),
                cst_icms=(profile.cst_icms if profile else ""),
                origem=(profile.origem if profile else "0"),
                pis_cst=(profile.pis_cst if profile else "49"),
                pis_rate=(profile.pis_rate if profile else 0),
                cofins_cst=(profile.cofins_cst if profile else "49"),
                cofins_rate=(profile.cofins_rate if profile else 0),
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


def _refresh_emission_for_retry(invoice, config):
    """Atualiza dhEmi e os dados locais derivados antes de uma retransmissao."""

    emission_dt = timezone.now()
    fiscal_payload = dict(invoice.fiscal_payload or {})
    access_key, numeric_code = build_access_key(
        uf=config.uf,
        emission_date=emission_dt,
        cnpj=config.cnpj,
        model=invoice.document_model,
        series=invoice.series,
        number=invoice.number,
        numeric_code=fiscal_payload.get("cNF"),
        emission_type=invoice.emission_type,
    )
    invoice.access_key = access_key
    invoice.qr_code_data = build_nfce_qrcode(
        access_key=access_key,
        environment=config.environment,
        csc_id=config.csc_id,
        csc_token=config.csc_token,
        base_url=config.qr_base_url,
    )
    fiscal_payload.update({"cNF": numeric_code, "emission": emission_dt.isoformat()})
    invoice.fiscal_payload = fiscal_payload
    invoice.issued_at = emission_dt


def resend_fiscal_invoice(invoice, *, user=None):
    """Retransmite somente a nota escolhida quando ela esta em contingencia/erro.

    Notas autorizadas, canceladas ou apenas processando em emissao normal nao
    podem ser reenviadas, evitando duplicidade no provedor. Uma nova rejeicao
    fica gravada como `error` para a tela mostrar o motivo real ao operador.
    """
    with transaction.atomic():
        locked = Invoice.all_objects.select_for_update().get(pk=invoice.pk)
        with tenant_context(locked.account):
            if locked.status in {Invoice.STATUS_ISSUED, Invoice.STATUS_CANCELLED}:
                raise ValidationError("Uma nota autorizada ou cancelada nao pode ser reenviada.")
            if locked.status != Invoice.STATUS_ERROR and not (
                locked.status == Invoice.STATUS_PENDING
                and locked.emission_type == Invoice.EMISSION_CONTINGENCY
            ):
                raise ValidationError(
                    "Somente notas em contingencia ou com erro podem ser reenviadas. "
                    "Para uma nota em processamento normal, atualize o status."
                )

            config = _resolve_fiscal_config(locked.restaurant, locked.branch)
            if config is None:
                raise ValidationError("Configuracao fiscal ativa nao encontrada para esta nota.")
            unavailable_reason = fiscal_provider_unavailable_reason(config)
            if unavailable_reason:
                raise ValidationError(unavailable_reason)

            _refresh_emission_for_retry(locked, config)
            try:
                get_provider(config.provider).emit(locked, config)
            except Exception as exc:  # noqa: BLE001 - a rejeicao precisa ficar visivel e persistida.
                locked.status = Invoice.STATUS_ERROR
                locked.error_message = str(exc)
            locked.updated_by = user
            locked.save()
            record_audit(
                action=AuditLog.ACTION_UPDATED,
                instance=locked,
                actor=user,
                metadata={"fiscal_resend": True, "status": locked.status},
            )
            return locked


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
            _refresh_emission_for_retry(invoice, config)
            try:
                get_provider(config.provider).emit(invoice, config)
            except Exception as exc:  # noqa: BLE001 — continua em contingencia, tenta de novo na proxima chamada.
                invoice.error_message = str(exc)
                invoice.save(
                    update_fields=[
                        "access_key",
                        "qr_code_data",
                        "fiscal_payload",
                        "issued_at",
                        "error_message",
                        "updated_at",
                    ]
                )
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


def print_fiscal_invoice(invoice, *, user=None, printer=None, manual_only=False):
    """Renderiza o DANFE NFC-e e cria o PrintJob (reaproveita o pipeline de impressao).

    `manual_only` diz que quem pediu foi um terminal, e que e ele quem vai
    imprimir. Nesse caso o cupom que a emissao automatica ja criou e assumido
    em vez de duplicado — a nota do cliente sai uma vez so.
    """
    from apps.printers.models import PrintJob
    from apps.printers.services import claim_pending_job

    with tenant_context(invoice.account):
        if manual_only and invoice.order_id:
            claimed = claim_pending_job(
                order=invoice.order, job_type=PrintJob.TYPE_FISCAL, printer=printer, user=user
            )
            if claimed is not None:
                return claimed
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


def _already_printed(order, job_type):
    """Ja existe um trabalho deste tipo para o pedido?

    Impressao automatica nao pode competir com a do PDV: o terminal cria o
    proprio trabalho ao concluir a venda (e imprime na hora, pela impressora
    master dele). Quem chegar primeiro imprime; o segundo desiste, em vez de
    sair um cupom duplicado da mesma venda.
    """
    from apps.printers.models import PrintJob

    return PrintJob.objects.filter(order=order, job_type=job_type).exists()


def print_sale_documents(order, *, invoice=None, user=None):
    """Imprime o recibo da venda e, quando houver, o DANFE da NFC-e.

    Sem impressora resolvida nao ha o que fazer: `resolve_printer_for` levanta
    `ValidationError` e o chamador registra o motivo. Um pedido pago nunca
    depende disto para continuar pago.
    """
    from apps.printers.models import PrintJob
    from apps.printers.services import register_print_job, resolve_printer_for

    jobs = []
    printer = resolve_printer_for(order, PrintJob.TYPE_RECEIPT)
    if not _already_printed(order, PrintJob.TYPE_RECEIPT):
        jobs.append(register_print_job(order=order, user=user, job_type=PrintJob.TYPE_RECEIPT, printer=printer))
    if invoice is not None and not _already_printed(order, PrintJob.TYPE_FISCAL):
        jobs.append(print_fiscal_invoice(invoice, user=user, printer=printer))
    return jobs


def issue_invoice_for_paid_order(order, *, user=None):
    """Emite a nota do pedido quitado e manda recibo e DANFE para a impressora.

    E o caminho automatico (`order_fully_paid`): o operador nao precisa voltar
    ao historico do pedido para emitir. Nada aqui pode derrubar o recebimento
    — ele ja foi gravado e commitado —, entao cada etapa registra o proprio
    motivo de falha e devolve o controle.

    Restaurante sem configuracao fiscal ativa nao e erro: e um restaurante que
    nao emite NFC-e. Nesse caso so o recibo da venda sai.
    """
    logger = logging.getLogger(__name__)
    invoice = None
    with tenant_context(order.account):
        reason = fiscal_emission_unavailable_reason(order)
        if reason:
            logger.info("Nota automatica dispensada para o pedido %s: %s", order.id, reason)
        else:
            existing = getattr(order, "invoice", None)
            if existing and existing.status in (Invoice.STATUS_PENDING, Invoice.STATUS_ISSUED):
                # O PDV pode ter emitido no mesmo instante; imprimir a que existe
                # e o comportamento certo, nao tentar montar uma segunda.
                invoice = existing
            else:
                try:
                    invoice = emit_fiscal_invoice(order, user=user)
                except (ValidationError, RuntimeError) as exc:
                    logger.warning("Falha ao emitir a nota do pedido %s: %s", order.id, exc)

        try:
            print_sale_documents(order, invoice=invoice, user=user)
        except (ValidationError, RuntimeError) as exc:
            logger.warning("Pedido %s pago, mas a impressao nao saiu: %s", order.id, exc)
    return invoice
