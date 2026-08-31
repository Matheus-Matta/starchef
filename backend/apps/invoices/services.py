"""
Servicos fiscais: emissao do documento a partir de um pedido e impressao do DANFE.

Monta toda a parte deterministica (numero, chave de acesso, QR, tributos, itens)
e delega a etapa externa (autorizacao SEFAZ) ao provider configurado — que no
scaffold e o ManualFiscalProvider (deixa a nota `pending`, sem protocolo).
"""
import base64
import io
import logging
import textwrap
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
    fiscal_invoice_issues,
    fiscal_profile_issues,
    format_access_key,
    only_digits,
)
from apps.invoices.models import FiscalConfig, Invoice, InvoiceItem
from apps.invoices.providers import (
    FiscalAmbiguous,
    FiscalConfigurationError,
    FiscalNotFound,
    FiscalProviderError,
    FiscalRejection,
    FiscalUnavailable,
    fiscal_provider_unavailable_reason,
    get_provider,
)
from apps.orders.models import Order, OrderItem


# Por que uma nota `pending` ainda nao esta autorizada. Fica em
# `Invoice.fiscal_payload["awaiting"]` porque decide o que a retransmissao deve
# fazer: transmitir de novo, apenas consultar, ou parar e pedir conferencia.
AWAITING_TRANSMISSION = "transmission"  # nunca chegou ao provedor
AWAITING_AUTHORIZATION = "authorization"  # provedor recebeu, SEFAZ ainda processa
AWAITING_RECONCILIATION = "reconciliation"  # pode ter sido emitida; reenviar duplicaria


# Por que uma nota parou em `error`. Distingue o que alguem consegue resolver
# corrigindo o cadastro do pedido do que exige mexer na configuracao da empresa.
FAILURE_REJECTION = "rejection"
FAILURE_CONFIGURATION = "configuration"


def _mark_awaiting(invoice, reason, message=""):
    payload = dict(invoice.fiscal_payload or {})
    payload["awaiting"] = reason
    payload.pop("failure", None)
    invoice.fiscal_payload = payload
    invoice.status = Invoice.STATUS_PENDING
    invoice.error_message = str(message or "")


def _mark_failed(invoice, kind, message):
    payload = dict(invoice.fiscal_payload or {})
    payload["failure"] = kind
    payload.pop("awaiting", None)
    invoice.fiscal_payload = payload
    invoice.status = Invoice.STATUS_ERROR
    invoice.error_message = str(message)


def fiscal_state_of(invoice):
    """Situacao fiscal detalhada, no vocabulario que o terminal grava na fila.

    `Invoice.status` sozinho nao basta: `pending` cobre desde "ainda nao saiu
    daqui" ate "pode ter sido emitida e nao sabemos". Quem esta offline precisa
    da diferenca para decidir entre reenviar, consultar ou parar.
    """
    if invoice is None:
        return "unknown"
    if invoice.status == Invoice.STATUS_ISSUED:
        return "authorized"
    if invoice.status == Invoice.STATUS_CANCELLED:
        return "cancelled"
    if invoice.status == Invoice.STATUS_ERROR:
        failure = (invoice.fiscal_payload or {}).get("failure")
        return "configuration_error" if failure == FAILURE_CONFIGURATION else "rejected"
    if invoice.status == Invoice.STATUS_PENDING:
        awaiting = (invoice.fiscal_payload or {}).get("awaiting")
        if awaiting == AWAITING_RECONCILIATION:
            return "reconciliation_required"
        if awaiting == AWAITING_AUTHORIZATION:
            return "processing"
        if invoice.emission_type == Invoice.EMISSION_CONTINGENCY:
            return "contingency_pending"
        return "awaiting_transmission"
    return "draft"


def with_fiscal_state(data, invoice):
    """Anexa a situacao fiscal real a um payload serializado da nota.

    `emitted` continua significando "o documento foi montado e aceito para
    transmissao" — e o que o frontend e o PDV ja consomem —, mas agora uma nota
    recusada devolve `False` em vez de `True`. O detalhe fica em `fiscal_state`.
    """
    data["fiscal_state"] = fiscal_state_of(invoice)
    data["emitted"] = invoice is not None and invoice.status in (
        Invoice.STATUS_PENDING,
        Invoice.STATUS_ISSUED,
    )
    data["printable"] = is_fiscally_printable(invoice)
    return data


def is_fiscally_printable(invoice):
    """Diz se ja existe documento fiscal que possa ser entregue ao consumidor.

    So um documento autorizado — ou uma contingencia de verdade, transmitida
    como tal — tem chave de acesso que a SEFAZ vai reconhecer. Uma nota que
    nunca saiu daqui tem chave montada localmente: imprimi-la entrega ao
    cliente um cupom cuja consulta no portal nunca vai encontrar nada.
    """
    if invoice is None:
        return False
    if invoice.status == Invoice.STATUS_ISSUED:
        return True
    # Notas antigas gravadas com tpEmis=9 pelo comportamento anterior seguem
    # imprimiveis: o cupom delas ja foi (ou seria) entregue com esse aviso.
    return invoice.emission_type == Invoice.EMISSION_CONTINGENCY


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


def billable_order_items(order):
    """Itens do pedido que entram na nota (fora cancelados e cortesias)."""
    return list(
        order.items.exclude(
            status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED]
        ).select_related("product")
    )


def rebuild_invoice_items(invoice, order, config, *, items=None, user=None):
    """Congela a tributacao de cada linha do pedido nos `InvoiceItem`.

    O `InvoiceItem` e um retrato: corrigir o cadastro do produto depois nao
    mexe numa nota ja emitida. Isso vale enquanto existir documento — mas uma
    nota que NUNCA foi transmitida nao e documento nenhum, e insistir na
    imutabilidade ali tornaria impossivel o gesto mais obvio do operador:
    corrigir o perfil fiscal que faltava e reenviar. Por isso a remontagem e
    reaproveitada pelo reenvio de notas que nunca sairam daqui.
    """
    if items is None:
        items = billable_order_items(order)

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
    return invoice


def apply_fiscal_profile_issues(invoice, config):
    """Registra as pendencias de cadastro e diz se elas impedem a transmissao.

    Devolve `(issues, blocked)`. Vale para a emissao e para o reenvio: um flag
    que so e checado numa das duas portas nao e um flag, e uma sugestao.
    """
    issues = fiscal_invoice_issues(invoice, config)
    payload = dict(invoice.fiscal_payload or {})
    if issues:
        payload["fiscal_profile_issues"] = issues
    else:
        payload.pop("fiscal_profile_issues", None)
    invoice.fiscal_payload = payload
    return issues, bool(issues) and config.strict_fiscal_profile


def _incomplete_profile_message(issues):
    return "Cadastro fiscal incompleto: " + " ".join(issue["message"] for issue in issues)


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

        items = billable_order_items(order)
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
        rebuild_invoice_items(invoice, order, config, items=items, user=user)
        invoice.fiscal_payload = {"cNF": numeric_code, "emission": emission_dt.isoformat()}

        # Parte externa (autorizacao SEFAZ). A venda ja esta paga, entao nenhuma
        # falha aqui pode travar o fechamento — mas o motivo da falha decide o
        # que acontece depois, e por isso cada familia e tratada em separado.
        #
        # O que NAO se faz mais: transformar qualquer excecao em tpEmis=9. Isso
        # marcava como "contingencia" ate uma rejeicao tributaria definitiva, e
        # produzia uma chave de contingencia que nunca era transmitida como tal
        # (o payload da Focus nao leva `forma_emissao`/`numero`/`serie`). O
        # cupom saia com uma chave que a SEFAZ jamais reconheceria. Contingencia
        # de verdade so volta com o agente fiscal local.
        # Cadastro fiscal incompleto deixa de ser invisivel. Com
        # `strict_fiscal_profile` ligado a nota nem e transmitida; com ele
        # desligado a emissao segue com os valores padrao do provider, mas o
        # que foi suprido fica REGISTRADO na nota e na auditoria — e e isso que
        # permite descobrir quem ainda depende deles antes de virar a chave.
        profile_issues, blocked = apply_fiscal_profile_issues(invoice, config)

        provider = get_provider(config.provider)
        if blocked:
            _mark_failed(invoice, FAILURE_REJECTION, _incomplete_profile_message(profile_issues))
            invoice.issued_at = emission_dt
            invoice.save()
            config.next_number = number + 1
            config.save(update_fields=["next_number", "updated_at"])
            record_audit(
                action=AuditLog.ACTION_CREATED,
                instance=invoice,
                actor=user,
                metadata={"access_key": access_key, "fiscal_profile_issues": len(profile_issues)},
            )
            return invoice

        try:
            provider.emit(invoice, config)
        except FiscalRejection as exc:
            # Recusa definitiva: reenviar repete a recusa. Precisa de correcao humana.
            _mark_failed(invoice, FAILURE_REJECTION, exc)
        except FiscalConfigurationError as exc:
            # Nenhuma nota da empresa sai enquanto isso nao for corrigido.
            _mark_failed(invoice, FAILURE_CONFIGURATION, exc)
        except FiscalAmbiguous as exc:
            # Pode ter sido emitida do outro lado: consultar antes de reenviar.
            _mark_awaiting(invoice, AWAITING_RECONCILIATION, exc)
        except FiscalUnavailable as exc:
            # Indisponibilidade momentanea: a retransmissao periodica resolve.
            _mark_awaiting(invoice, AWAITING_TRANSMISSION, exc)
        except Exception as exc:  # noqa: BLE001 — falha inesperada nao pode virar 500 no caixa.
            logging.getLogger(__name__).exception("Falha inesperada ao emitir a nota do pedido %s", order.id)
            _mark_failed(invoice, FAILURE_REJECTION, exc)
        else:
            if invoice.status == Invoice.STATUS_PENDING and provider.transmits:
                # O provider aceitou mas a SEFAZ ainda processa: so consultar.
                _mark_awaiting(invoice, AWAITING_AUTHORIZATION)
        invoice.issued_at = emission_dt
        invoice.save()

        config.next_number = number + 1
        config.save(update_fields=["next_number", "updated_at"])

        record_audit(
            action=AuditLog.ACTION_CREATED,
            instance=invoice,
            actor=user,
            metadata={
                "access_key": access_key,
                **({"fiscal_profile_issues": len(profile_issues)} if profile_issues else {}),
            },
        )
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
            config = _resolve_fiscal_config(locked.restaurant, locked.branch)
            if config is None:
                raise ValidationError("Configuracao fiscal ativa nao encontrada para esta nota.")
            unavailable_reason = fiscal_provider_unavailable_reason(config)
            if unavailable_reason:
                raise ValidationError(unavailable_reason)

            awaiting = (locked.fiscal_payload or {}).get("awaiting")
            if awaiting == AWAITING_RECONCILIATION:
                # O provedor pode ja ter o documento. Consultar e a unica acao
                # segura: um POST novo criaria uma segunda nota.
                try:
                    get_provider(config.provider).status(locked)
                except FiscalNotFound as exc:
                    _mark_awaiting(locked, AWAITING_TRANSMISSION, exc)
                except FiscalUnavailable as exc:
                    _mark_awaiting(locked, AWAITING_RECONCILIATION, exc)
                except FiscalConfigurationError as exc:
                    _mark_failed(locked, FAILURE_CONFIGURATION, exc)
                except FiscalProviderError as exc:
                    _mark_failed(locked, FAILURE_REJECTION, exc)
                locked.updated_by = user
                locked.save()
                ensure_fiscal_print_job(locked, user=user)
                record_audit(
                    action=AuditLog.ACTION_UPDATED,
                    instance=locked,
                    actor=user,
                    metadata={"fiscal_reconciled": True, "status": locked.status},
                )
                return locked

            resendable = locked.status == Invoice.STATUS_ERROR or (
                locked.status == Invoice.STATUS_PENDING
                and (
                    locked.emission_type == Invoice.EMISSION_CONTINGENCY
                    or awaiting == AWAITING_TRANSMISSION
                )
            )
            if not resendable:
                raise ValidationError(
                    "Somente notas nao transmitidas, em contingencia ou com erro podem ser reenviadas. "
                    "Para uma nota em processamento normal, atualize o status."
                )

            # A nota nunca foi transmitida, entao o retrato dela pode (e deve)
            # ser refeito com o cadastro de agora: e o que faz "corrigi o perfil
            # fiscal e reenviei" funcionar. Sem isso o reenvio repetia o NCM
            # vazio congelado na emissao e mandava `00000000` de novo.
            if locked.order_id:
                rebuild_invoice_items(locked, locked.order, config, user=user)
            profile_issues, blocked = apply_fiscal_profile_issues(locked, config)
            if blocked:
                _mark_failed(locked, FAILURE_REJECTION, _incomplete_profile_message(profile_issues))
                locked.updated_by = user
                locked.save()
                record_audit(
                    action=AuditLog.ACTION_UPDATED,
                    instance=locked,
                    actor=user,
                    metadata={
                        "fiscal_resend": True,
                        "status": locked.status,
                        "fiscal_profile_issues": len(profile_issues),
                    },
                )
                return locked

            _refresh_emission_for_retry(locked, config)
            try:
                get_provider(config.provider).emit(locked, config)
            except FiscalAmbiguous as exc:
                _mark_awaiting(locked, AWAITING_RECONCILIATION, exc)
            except FiscalUnavailable as exc:
                _mark_awaiting(locked, AWAITING_TRANSMISSION, exc)
            except FiscalConfigurationError as exc:
                _mark_failed(locked, FAILURE_CONFIGURATION, exc)
            except Exception as exc:  # noqa: BLE001 - a rejeicao precisa ficar visivel e persistida.
                _mark_failed(locked, FAILURE_REJECTION, exc)
            else:
                if locked.status == Invoice.STATUS_PENDING:
                    _mark_awaiting(locked, AWAITING_AUTHORIZATION)
            locked.updated_by = user
            locked.save()
            ensure_fiscal_print_job(locked, user=user)
            record_audit(
                action=AuditLog.ACTION_UPDATED,
                instance=locked,
                actor=user,
                metadata={"fiscal_resend": True, "status": locked.status},
            )
            return locked


def reprocess_pending_fiscal_invoices(*, account=None):
    """Reprocessa as notas que ficaram `pending` e devolve (retried, issued).

    Chamado por `manage.py reprocess_pending_invoices`, manualmente ou por
    agendamento futuro (Celery beat) — cada nota e independente, uma falha nao
    trava as demais.

    O que se faz com a nota depende de por que ela esta pendente, gravado em
    `fiscal_payload["awaiting"]`:

    * `transmission` — nunca chegou ao provedor: transmite de novo;
    * `authorization` — o provedor recebeu e a SEFAZ ainda processa: so consulta,
      porque um POST novo criaria um segundo documento;
    * `reconciliation` — a resposta se perdeu depois do envio: so consulta, pelo
      mesmo motivo, e com mais razao ainda.

    Notas antigas em tpEmis=9, gravadas pelo comportamento anterior, entram como
    `transmission`: e o unico tratamento que faz sentido para elas.

    Varre TODAS as contas (`all_objects`, nao o manager escopado por tenant):
    isso roda fora do ciclo de uma unica requisicao/conta, entao nao ha um
    tenant "atual" — cada nota e reprocessada dentro do proprio `tenant_context`.
    """
    logger = logging.getLogger(__name__)
    queryset = Invoice.all_objects.filter(status=Invoice.STATUS_PENDING)
    if account is not None:
        queryset = queryset.filter(account=account)

    retried = 0
    issued = 0
    for invoice in queryset.select_related("branch", "restaurant"):
        with tenant_context(invoice.account):
            config = _resolve_fiscal_config(invoice.restaurant, invoice.branch)
            if not config:
                continue
            provider = get_provider(config.provider)
            awaiting = (invoice.fiscal_payload or {}).get("awaiting")
            if awaiting is None and invoice.emission_type == Invoice.EMISSION_CONTINGENCY:
                awaiting = AWAITING_TRANSMISSION
            if awaiting is None or not provider.transmits:
                continue
            retried += 1
            try:
                if awaiting == AWAITING_TRANSMISSION:
                    _refresh_emission_for_retry(invoice, config)
                    provider.emit(invoice, config)
                else:
                    provider.status(invoice)
            except FiscalNotFound as exc:
                # O provedor nao tem o documento: nada foi emitido, entao
                # retransmitir nao duplica. Resolve a reconciliacao.
                _mark_awaiting(invoice, AWAITING_TRANSMISSION, exc)
            except FiscalAmbiguous as exc:
                _mark_awaiting(invoice, AWAITING_RECONCILIATION, exc)
            except FiscalUnavailable as exc:
                # Continua pendente pelo mesmo motivo; tenta de novo na proxima chamada.
                _mark_awaiting(invoice, awaiting, exc)
            except FiscalConfigurationError as exc:
                # Parar de insistir: nenhuma nota sai ate a configuracao mudar.
                _mark_failed(invoice, FAILURE_CONFIGURATION, exc)
            except FiscalProviderError as exc:
                # Rejeicao: reenviar repetiria a recusa.
                _mark_failed(invoice, FAILURE_REJECTION, exc)
            except Exception as exc:  # noqa: BLE001 — uma nota nao pode derrubar o lote.
                logger.exception("Falha inesperada ao reprocessar a nota %s", invoice.id)
                invoice.error_message = str(exc)
            else:
                if invoice.status == Invoice.STATUS_PENDING:
                    _mark_awaiting(invoice, AWAITING_AUTHORIZATION)
            invoice.save()
            if invoice.status == Invoice.STATUS_ISSUED:
                issued += 1
                # A autorizacao chegou agora; o cupom do cliente ainda nao saiu.
                ensure_fiscal_print_job(invoice)
                record_audit(action=AuditLog.ACTION_UPDATED, instance=invoice, metadata={"reprocessed": True})
    return retried, issued


def fiscal_readiness(config, *, products=None):
    """Conferencia de pre-voo: da para vender com NFC-e hoje?

    Responde a pergunta na hora certa — antes da primeira venda do turno — em
    vez de deixar o cadastro incompleto aparecer depois do pagamento, quando o
    cliente ja foi embora e a unica saida e uma nota recusada.

    Cobre as duas metades: o cadastro do EMITENTE (as mesmas pendencias que a
    sincronizacao com a Focus ja checa) e o cadastro dos PRODUTOS ativos.
    """
    from apps.invoices.focus import company_payload_missing_fields
    from apps.menu.models import Product

    with tenant_context(config.account):
        company_issues = company_payload_missing_fields(config)
        if products is None:
            products = (
                Product.objects.filter(restaurant=config.restaurant, is_active=True)
                .select_related("fiscal_profile")
                .order_by("name")
            )

        products = list(products)
        product_reports = []
        for product in products:
            profile = product.fiscal_profile or config.default_profile
            issues = fiscal_profile_issues(profile, crt=config.crt, subject=product.name)
            if issues:
                product_reports.append(
                    {
                        "product": str(product.id),
                        "name": product.name,
                        "internal_code": product.internal_code,
                        "fiscal_profile": str(profile.id) if profile else None,
                        "issues": issues,
                    }
                )

        return {
            "ready": not company_issues and not product_reports,
            "strict": config.strict_fiscal_profile,
            "company_issues": company_issues,
            "products_checked": len(products),
            "products_with_issues": len(product_reports),
            "products": product_reports,
        }


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


def _danfe_decimal(value, places=2):
    return f"{Decimal(value):.{places}f}".replace(".", ",")


def _danfe_linha_valor(rotulo, valor, *, places=2):
    quantia = _danfe_decimal(valor, places)
    largura_rotulo = _DANFE_WIDTH - len(quantia) - 1
    rotulo = str(rotulo)[:largura_rotulo]
    return f"{rotulo:<{largura_rotulo}} {quantia}"


def _danfe_center_wrapped(value):
    return [line.center(_DANFE_WIDTH) for line in textwrap.wrap(str(value), _DANFE_WIDTH) or [""]]


def _danfe_payment_label(payment):
    label = payment.payment_method.name.upper()
    if payment.card_subtype:
        label += f" - {payment.get_card_subtype_display().upper()}"
    return label


def _danfe_nfce_text(invoice, config):
    """Renderiza o DANFE NFC-e em texto monoespaçado 48 colunas.

    Mesmo conteudo do template HTML (`danfe_nfce.html`) — necessario porque o
    agente local de impressao so consegue mandar bytes ESC/POS puros pra
    impressoras de rede/serial; so a via de spool do Windows renderiza HTML.
    """
    lines = []
    name = (
        ((config.trade_name or config.corporate_name) if config else "")
        or invoice.emitter_name
        or "RAZAO SOCIAL"
    )
    lines.append(name.center(_DANFE_WIDTH)[:_DANFE_WIDTH])
    cnpj = invoice.emitter_cnpj or "__.___.___/____-__"
    ie = f" IE: {config.ie}" if config and config.ie else ""
    lines.append(f"CNPJ: {cnpj}{ie}".center(_DANFE_WIDTH)[:_DANFE_WIDTH])
    if config and (config.address_line or config.city):
        address = config.address_line
        if config.address_number:
            address += f", {config.address_number}"
        if config.district:
            address += f" - {config.district}"
        if config.city:
            address += f" - {config.city}/{config.uf}"
        if config.zip_code:
            address += f" - CEP {config.zip_code}"
        lines.extend(_danfe_center_wrapped(address))
    lines.append("-" * _DANFE_WIDTH)
    lines.append("DOCUMENTO AUXILIAR DA NOTA FISCAL DE".center(_DANFE_WIDTH))
    lines.append("CONSUMIDOR ELETRONICA".center(_DANFE_WIDTH))
    if invoice.environment == FiscalConfig.ENV_HOMOLOGATION:
        lines.append("-" * _DANFE_WIDTH)
        lines.append("SEM VALOR FISCAL - HOMOLOGACAO".center(_DANFE_WIDTH))
    if invoice.emission_type == Invoice.EMISSION_CONTINGENCY:
        lines.append("-" * _DANFE_WIDTH)
        lines.append("EMITIDA EM CONTINGENCIA".center(_DANFE_WIDTH))
        lines.append("TRANSMITIR QUANDO A CONEXAO VOLTAR".center(_DANFE_WIDTH))
    lines.append("-" * _DANFE_WIDTH)

    lines.append("COD DESCRICAO          QTD UN VL UNIT VL TOTAL")
    for item in invoice.items.all():
        description = f"{item.code or '-'} {item.description}"
        lines.extend(textwrap.wrap(description, _DANFE_WIDTH) or [description[:_DANFE_WIDTH]])
        detail = f"{_danfe_decimal(item.quantity, 3)} {item.unit.upper()} x {_danfe_decimal(item.unit_price)}"
        lines.append(_danfe_linha_valor(f"  {detail}", item.total_price))

    lines.append("-" * _DANFE_WIDTH)
    lines.append(_danfe_linha_valor("QTD. TOTAL DE ITENS", invoice.items.count(), places=0))
    lines.append(_danfe_linha_valor("VALOR TOTAL R$", invoice.total_amount))
    if invoice.discount_total:
        lines.append(_danfe_linha_valor("DESCONTO R$", invoice.discount_total))
    if invoice.tax_approx_total:
        lines.append(_danfe_linha_valor("TRIBUTOS APROX. R$", invoice.tax_approx_total))
    lines.append("-" * _DANFE_WIDTH)

    lines.append("FORMA DE PAGAMENTO" + "VALOR PAGO".rjust(_DANFE_WIDTH - len("FORMA DE PAGAMENTO")))
    payments = invoice.order.payments.select_related("payment_method").filter(status="approved").order_by("created_at")
    if payments.exists():
        for payment in payments:
            lines.append(_danfe_linha_valor(_danfe_payment_label(payment), payment.amount))
            if payment.change_amount:
                lines.append(_danfe_linha_valor("TROCO", payment.change_amount))
    else:
        lines.append(_danfe_linha_valor("NAO INFORMADO", invoice.total_amount))
    lines.append("-" * _DANFE_WIDTH)

    lines.append("Via Consumidor".center(_DANFE_WIDTH))
    lines.append("Consulte pela Chave de Acesso em".center(_DANFE_WIDTH))
    consult_url = invoice.consult_url or (config.portal_url if config else "") or "(portal da SEFAZ da UF)"
    lines.extend(_danfe_center_wrapped(consult_url))
    lines.extend(_danfe_center_wrapped(format_access_key(invoice.access_key)))
    lines.append(f"NFC-e n. {invoice.number}  Serie {invoice.series}".center(_DANFE_WIDTH)[:_DANFE_WIDTH])
    if invoice.issued_at:
        lines.append(f"Emissao: {timezone.localtime(invoice.issued_at):%d/%m/%Y %H:%M:%S}".center(_DANFE_WIDTH))

    if invoice.authorization_protocol:
        lines.extend(_danfe_center_wrapped(f"PROTOCOLO DE AUTORIZACAO: {invoice.authorization_protocol}"))
        if invoice.authorized_at:
            lines.append(
                f"DATA DE AUTORIZACAO: {timezone.localtime(invoice.authorized_at):%d/%m/%Y %H:%M:%S}".center(
                    _DANFE_WIDTH
                )
            )
    else:
        lines.append("AGUARDANDO AUTORIZACAO".center(_DANFE_WIDTH))
        lines.extend(_danfe_center_wrapped("(protocolo sera preenchido apos transmissao a SEFAZ)"))
    lines.append("-" * _DANFE_WIDTH)

    if invoice.recipient_cpf:
        lines.extend(_danfe_center_wrapped(f"CONSUMIDOR - CPF: {invoice.recipient_cpf}"))
        if invoice.recipient_name:
            lines.extend(_danfe_center_wrapped(invoice.recipient_name.upper()))
    else:
        lines.append("CONSUMIDOR NAO IDENTIFICADO".center(_DANFE_WIDTH))
    lines.append("-" * _DANFE_WIDTH)
    return "\n".join(lines)


def print_fiscal_invoice(invoice, *, user=None, printer=None, manual_only=False):
    """Renderiza o DANFE NFC-e e cria o PrintJob (reaproveita o pipeline de impressao).

    `manual_only` diz que quem pediu foi um terminal, e que e ele quem vai
    imprimir. Nesse caso o cupom que a emissao automatica ja criou e assumido
    em vez de duplicado — a nota do cliente sai uma vez so.
    """
    from apps.printers.models import PrintJob
    from apps.printers.services import claim_pending_job

    if not is_fiscally_printable(invoice):
        raise ValidationError(
            "A NFC-e ainda nao foi autorizada, entao o DANFE nao pode ser impresso: "
            "a chave impressa nao existiria na SEFAZ. Reenvie a nota e imprima depois "
            "da autorizacao."
        )

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
            "payments": invoice.order.payments.select_related("payment_method")
            .filter(status="approved")
            .order_by("created_at"),
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
    # Nota ainda nao autorizada nao gera DANFE: o recibo da venda sai, o cupom
    # fiscal sai quando (e se) a autorizacao chegar. Ver `is_fiscally_printable`.
    if is_fiscally_printable(invoice) and not _already_printed(order, PrintJob.TYPE_FISCAL):
        jobs.append(print_fiscal_invoice(invoice, user=user, printer=printer))
    return jobs


def refresh_fiscal_invoice_status(invoice, *, user=None):
    """Consulta o provedor e persiste a situacao real da nota.

    Antes isto vivia na view e chamava `get_provider(invoice.provider)`. O campo
    `provider` so e gravado quando a emissao chega ao provedor, entao numa nota
    que nunca saiu daqui ele esta vazio — e `get_provider("")` devolve o
    provedor Manual, cujo `status()` apenas repete o que ja estava no banco. A
    consulta respondia 200 sem ter consultado nada.

    Agora o provedor sai da configuracao quando o campo esta vazio, e quem nao
    transmite recusa a consulta com o motivo em vez de fingir que consultou.
    """
    with transaction.atomic():
        locked = Invoice.all_objects.select_for_update().get(pk=invoice.pk)
        with tenant_context(locked.account):
            config = _resolve_fiscal_config(locked.restaurant, locked.branch)
            if config is None:
                raise ValidationError("Configuracao fiscal ativa nao encontrada para esta nota.")

            provider = get_provider(locked.provider or config.provider)
            if not provider.transmits:
                raise ValidationError(
                    "Esta nota nunca foi transmitida a um provedor fiscal, entao nao ha "
                    "situacao a consultar. Use o reenvio para transmiti-la."
                )

            try:
                provider.status(locked)
            except FiscalNotFound as exc:
                # O provedor nao conhece esta referencia: o documento nao existe
                # la. E a resposta que resolve uma nota presa em reconciliacao.
                _mark_awaiting(locked, AWAITING_TRANSMISSION, exc)
            except FiscalUnavailable as exc:
                raise ValidationError(str(exc)) from exc
            except FiscalConfigurationError as exc:
                _mark_failed(locked, FAILURE_CONFIGURATION, exc)
            except FiscalProviderError as exc:
                _mark_failed(locked, FAILURE_REJECTION, exc)
            else:
                if locked.status == Invoice.STATUS_PENDING:
                    _mark_awaiting(locked, AWAITING_AUTHORIZATION)

            locked.updated_by = user
            locked.save()
            # A consulta pode ter sido o momento em que a nota virou autorizada.
            ensure_fiscal_print_job(locked, user=user)
            record_audit(
                action=AuditLog.ACTION_UPDATED,
                instance=locked,
                actor=user,
                metadata={"fiscal_refresh": True, "status": locked.status},
            )
            return locked


def ensure_fiscal_print_job(invoice, *, user=None):
    """Enfileira o DANFE de uma nota que foi autorizada DEPOIS do pagamento.

    Sem isto, a venda offline terminava sem cupom fiscal nenhum: o DANFE nao
    sai mais no pagamento (a nota ainda nao existe na SEFAZ) e nada criava o
    trabalho quando a autorizacao chegava — a nota ficava autorizada no banco e
    o cliente nunca recebia o documento. Alguem precisava abrir o pedido e
    clicar em imprimir, sem nenhum aviso de que precisava.

    Idempotente por pedido: `_already_printed` impede um segundo cupom da mesma
    venda, entao chamar isto em todo caminho que autoriza uma nota e seguro.
    Nunca levanta — impressora fora do ar nao pode desfazer uma autorizacao que
    ja aconteceu, nem derrubar o lote de reprocessamento.
    """
    from apps.printers.models import PrintJob
    from apps.printers.services import resolve_printer_for

    logger = logging.getLogger(__name__)
    if not is_fiscally_printable(invoice) or not invoice.order_id:
        return None
    try:
        with tenant_context(invoice.account):
            order = invoice.order
            if _already_printed(order, PrintJob.TYPE_FISCAL):
                return None
            printer = resolve_printer_for(order, PrintJob.TYPE_FISCAL)
            return print_fiscal_invoice(invoice, user=user, printer=printer)
    except (ValidationError, RuntimeError) as exc:
        logger.warning(
            "Nota %s autorizada, mas o DANFE nao foi enfileirado: %s", invoice.id, exc
        )
        return None


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
