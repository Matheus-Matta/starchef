import logging
import re
from celery import shared_task
from django.db import transaction, IntegrityError
from django.utils import timezone
from datetime import timedelta
from apps.inbound_nfe.models import (
    DFeSyncState, DFeDistributionDocument, InboundNFe, InboundNFeItem
)
from apps.inbound_nfe.services.sefaz_client import NFeDistribuicaoClient
from apps.inbound_nfe.services.xml_parser import (
    parse_nfe_xml, detect_document_type
)

logger = logging.getLogger(__name__)

# Limites de segurança
MAX_PAGES_PER_SYNC = 50       # Máximo de páginas por execução (evita loop infinito)
COOLDOWN_NO_DOCS_MIN = 65     # cStat 137: nenhum documento
COOLDOWN_END_PAGES_MIN = 60   # Fim da paginação (ultNSU == maxNSU)
COOLDOWN_ERROR_MIN = 30       # Erro genérico
COOLDOWN_BLOCKED_HOURS = 2    # cStat 656: consumo indevido
COOLDOWN_BETWEEN_PAGES_SEC = 2  # Intervalo entre páginas para não sobrecarregar


IBGE_UF_MAP = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
    "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
    "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41",
    "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53",
}


def _resolve_uf_code(uf: str) -> str:
    uf_clean = (uf or "").strip().upper()
    if uf_clean.isdigit():
        return uf_clean
    return IBGE_UF_MAP.get(uf_clean, "35")


# ─────────────────────────────────────────────────────────────────────────────
# TASKS AGENDADAS
# ─────────────────────────────────────────────────────────────────────────────

@shared_task
def sync_all_inbound_nfe():
    """
    Agendador principal (Celery Beat, ~1h).
    Busca todos os FiscalConfig com certificado e enfileira sync por estado.
    """
    from apps.invoices.models import FiscalConfig

    for config in FiscalConfig.objects.filter(is_active=True):
        if not (config.certificate_file or config.certificate_ref):
            continue

        cnpj = re.sub(r'\D', '', config.cnpj or config.certificate_cnpj or '')
        if not cnpj:
            continue

        environment = (
            "homologation"
            if config.environment == FiscalConfig.ENV_HOMOLOGATION
            else "production"
        )

        state, _ = DFeSyncState.objects.get_or_create(
            account=config.account,
            branch=config.branch,
            restaurant=config.restaurant,
            defaults={
                'cnpj': cnpj,
                'environment': environment,
            }
        )
        # Atualizar CNPJ/environment se mudou no FiscalConfig
        if state.cnpj != cnpj or state.environment != environment:
            state.cnpj = cnpj
            state.environment = environment
            state.save(update_fields=['cnpj', 'environment'])

        sync_branch_inbound_nfe.delay(state.id)


@shared_task
def sync_branch_inbound_nfe(state_id):
    """
    Sincroniza um CNPJ específico, usando lock atômico.
    """
    try:
        with transaction.atomic():
            state = DFeSyncState.objects.select_for_update(nowait=True).get(
                id=state_id
            )

            if state.is_syncing:
                logger.info(f"SyncState {state.id} já em andamento. Ignorando.")
                return

            now = timezone.now()
            if state.next_allowed_at and state.next_allowed_at > now:
                logger.info(
                    f"SyncState {state.id} em cooldown até "
                    f"{state.next_allowed_at}."
                )
                return

            state.is_syncing = True
            state.save(update_fields=['is_syncing'])

    except Exception as e:
        logger.warning(
            f"Não foi possível obter lock para SyncState {state_id}: {e}"
        )
        return

    try:
        _perform_sync(state)
    except Exception as e:
        logger.error(f"Erro durante sincronização do estado {state_id}: {e}")
    finally:
        with transaction.atomic():
            state.refresh_from_db()
            state.is_syncing = False
            state.save(update_fields=['is_syncing'])


# ─────────────────────────────────────────────────────────────────────────────
# SINCRONIZAÇÃO COM SEFAZ (DOWNLOAD)
# ─────────────────────────────────────────────────────────────────────────────

def _perform_sync(state: DFeSyncState):
    """
    Comunicação efetiva com a SEFAZ com paginação segura.
    Separa DOWNLOAD (salvar XMLs brutos) de PROCESSAMENTO (interpretar XMLs).

    Loop de paginação:
      - cStat 138 + ultNSU < maxNSU → próxima página
      - cStat 138 + ultNSU == maxNSU → parar
      - cStat 137 → parar (nenhum documento)
      - cStat 656 → parar (consumo indevido)
      - Qualquer outro → parar (erro)
    """
    import time
    from apps.invoices.models import FiscalConfig

    account = state.account
    config = FiscalConfig.all_objects.filter(
        account=account,
        restaurant_id=state.restaurant_id
    ).first() or FiscalConfig.all_objects.filter(account=account).first()

    # Resolver CNPJ
    cnpj = state.cnpj
    if not cnpj:
        cnpj_raw = ""
        if config:
            cnpj_raw = config.cnpj or config.certificate_cnpj
        if not cnpj_raw and state.restaurant:
            cnpj_raw = getattr(state.restaurant, 'cnpj', '')
        cnpj = re.sub(r'\D', '', cnpj_raw or '')

    # Resolver UF
    uf_raw = (
        (config.uf if config else '')
        or (state.restaurant.state if state.restaurant else '')
    )
    uf_code = _resolve_uf_code(uf_raw)

    # Resolver ambiente
    environment = state.environment or "production"

    client = NFeDistribuicaoClient(
        account=account,
        restaurant_id=state.restaurant_id,
        environment=environment
    )

    pages = 0
    current_ult_nsu = state.ult_nsu

    while pages < MAX_PAGES_PER_SYNC:
        pages += 1

        try:
            response = client.fetch_since_nsu(
                cnpj=cnpj,
                uf_code=uf_code,
                ult_nsu=current_ult_nsu
            )
        except Exception as e:
            logger.error(
                f"Erro de comunicação com SEFAZ (página {pages}): {e}"
            )
            state.sync_error_count += 1
            state.last_reason = f"Erro: {e}"
            # ATENÇÃO: NÃO aplicar cooldown para erros de execução local ou de rede sem resposta da SEFAZ.
            state.save(update_fields=['sync_error_count', 'last_reason'])
            raise e

        state.last_cstat = response.cstat
        state.last_reason = response.reason
        state.last_sync_at = timezone.now()

        # ── cStat 138: Documentos localizados ──
        if response.cstat == '138':
            state.sync_error_count = 0

            # PONTO 10: Atomicidade — salvar XMLs e NSU na mesma transação
            with transaction.atomic():
                saved_count = _save_raw_documents(
                    response.documents, state
                )

                # PONTO 2: Só atualizar NSU se a SEFAZ retornou valor válido
                if response.ult_nsu is not None:
                    state.ult_nsu = response.ult_nsu
                    current_ult_nsu = response.ult_nsu
                if response.max_nsu is not None:
                    state.max_nsu = response.max_nsu

                state.save(update_fields=[
                    'ult_nsu', 'max_nsu', 'last_cstat',
                    'last_reason', 'last_sync_at', 'sync_error_count'
                ])

            logger.info(
                f"Página {pages}: {saved_count} docs salvos, "
                f"ultNSU={state.ult_nsu}, maxNSU={state.max_nsu}"
            )

            # PONTO 8: Paginação — continuar enquanto ultNSU < maxNSU
            if (
                response.ult_nsu
                and response.max_nsu
                and response.ult_nsu < response.max_nsu
            ):
                # Pausa entre páginas para não sobrecarregar
                time.sleep(COOLDOWN_BETWEEN_PAGES_SEC)
                continue
            else:
                # Fim da paginação
                state.next_allowed_at = timezone.now() + timedelta(
                    minutes=COOLDOWN_END_PAGES_MIN
                )
                state.save(update_fields=['next_allowed_at'])
                break

        # ── cStat 137: Nenhum documento localizado ──
        elif response.cstat == '137':
            state.sync_error_count = 0
            state.next_allowed_at = timezone.now() + timedelta(
                minutes=COOLDOWN_NO_DOCS_MIN
            )
            state.save(update_fields=[
                'last_cstat', 'last_reason', 'last_sync_at',
                'next_allowed_at', 'sync_error_count'
            ])
            logger.info(
                f"SyncState {state.id}: cStat 137 — nenhum documento. "
                f"Próxima consulta após {state.next_allowed_at}."
            )
            break

        # ── cStat 656: Consumo indevido ──
        elif response.cstat == '656':
            state.sync_error_count += 1

            # Se a SEFAZ informou o ultNSU correto a ser utilizado (ex: 000000000000050)
            if response.ult_nsu and response.ult_nsu != "000000000000000":
                logger.info(
                    f"SyncState {state.id}: cStat 656 forneceu ultNSU={response.ult_nsu}. "
                    f"Atualizando NSU para próxima consulta."
                )
                state.ult_nsu = response.ult_nsu

            # Calcular momento exato permitido para a próxima consulta (dhResp + 65 min)
            base_time = response.dh_resp if response.dh_resp is not None else timezone.now()
            state.next_allowed_at = base_time + timedelta(minutes=COOLDOWN_NO_DOCS_MIN)

            state.save(update_fields=[
                'last_cstat', 'last_reason', 'last_sync_at',
                'next_allowed_at', 'ult_nsu', 'sync_error_count'
            ])
            logger.error(
                f"SyncState {state.id}: cStat 656 — CONSUMO INDEVIDO. "
                f"ultNSU={state.ult_nsu}, bloqueado até {state.next_allowed_at}."
            )
            break

        # ── Qualquer outro cStat: erro/rejeição ──
        else:
            state.sync_error_count += 1
            state.next_allowed_at = timezone.now() + timedelta(
                minutes=COOLDOWN_ERROR_MIN
            )
            state.save(update_fields=[
                'last_cstat', 'last_reason', 'last_sync_at',
                'next_allowed_at', 'sync_error_count'
            ])
            logger.warning(
                f"SyncState {state.id}: cStat {response.cstat} — "
                f"{response.reason}. Cooldown {COOLDOWN_ERROR_MIN}min."
            )
            break

    # PONTO 12: Separação download/processamento — enfileirar processamento
    try:
        process_pending_dfe_documents.delay(str(state.account_id))
    except Exception as e:
        logger.warning(f"Erro ao enfileirar no Celery, executando síncrono: {e}")
        try:
            process_pending_dfe_documents(str(state.account_id))
        except Exception as e2:
            logger.error(f"Erro ao processar documentos DF-e pendentes: {e2}")


def fetch_and_process_specific_nsu(account, restaurant, nsu: str) -> dict:
    """
    Realiza uma consulta pontual por NSU (consNSU) na SEFAZ,
    salva o documento bruto recebido em DFeDistributionDocument
    e processa a NF-e e seus itens imediatamente.
    """
    from apps.invoices.models import FiscalConfig

    config = FiscalConfig.all_objects.filter(
        account=account,
        restaurant=restaurant
    ).first() or FiscalConfig.all_objects.filter(account=account).first()

    cnpj_raw = ""
    if config:
        cnpj_raw = config.cnpj or config.certificate_cnpj
    if not cnpj_raw and restaurant:
        cnpj_raw = getattr(restaurant, 'cnpj', '')
    cnpj = re.sub(r'\D', '', cnpj_raw or '')

    uf_raw = (
        (config.uf if config else '')
        or (restaurant.state if restaurant else '')
    )
    uf_code = _resolve_uf_code(uf_raw)
    environment = (
        "homologation"
        if config and config.environment == FiscalConfig.ENV_HOMOLOGATION
        else "production"
    )

    client = NFeDistribuicaoClient(
        account=account,
        restaurant_id=restaurant.id if restaurant else None,
        environment=environment
    )

    clean_nsu = str(nsu).strip().zfill(15)
    response = client.fetch_nsu(cnpj=cnpj, uf_code=uf_code, nsu=clean_nsu)

    saved_count = 0
    processed_count = 0
    created_invoices = []

    for doc in response.documents:
        doc_type = detect_document_type(doc.schema)
        dist_doc, _ = DFeDistributionDocument.all_objects.get_or_create(
            account=account,
            nsu=doc.nsu,
            defaults={
                'branch': config.branch if config else None,
                'restaurant': restaurant,
                'schema': doc.schema,
                'document_type': doc_type,
                'xml': doc.xml,
                'processing_status': DFeDistributionDocument.PROCESSING_PENDING,
            }
        )
        saved_count += 1

        try:
            _process_single_document(dist_doc)
            processed_count += 1
            if dist_doc.access_key:
                inv = InboundNFe.all_objects.filter(account=account, access_key=dist_doc.access_key).first()
                if inv:
                    created_invoices.append({
                        'id': str(inv.id),
                        'access_key': inv.access_key,
                        'number': inv.number,
                        'series': inv.series,
                        'supplier_name': inv.supplier_name,
                        'supplier_cnpj': inv.supplier_cnpj,
                        'total_invoice': float(inv.total_invoice),
                        'items_count': inv.items.count(),
                    })
        except Exception as exc:
            logger.error(f"Erro ao processar NSU={clean_nsu}: {exc}")

    return {
        'cstat': response.cstat,
        'reason': response.reason,
        'ult_nsu': response.ult_nsu,
        'max_nsu': response.max_nsu,
        'saved_count': saved_count,
        'processed_count': processed_count,
        'invoices': created_invoices,
    }


def _save_raw_documents(documents, state: DFeSyncState) -> int:
    """
    Salva os documentos brutos no DFeDistributionDocument.
    Retorna a quantidade de documentos novos salvos.
    Idempotente: constraint (account, nsu) impede duplicatas.
    """
    saved = 0
    for doc in documents:
        doc_type = detect_document_type(doc.schema)
        # Evita quebrar a transação atômica verificando existência prévia
        if DFeDistributionDocument.all_objects.filter(account=state.account, nsu=doc.nsu).exists():
            logger.debug(f"Documento NSU={doc.nsu} já existe. Ignorando.")
            continue

        try:
            with transaction.atomic():
                DFeDistributionDocument.all_objects.create(
                    account=state.account,
                    branch=state.branch,
                    restaurant=state.restaurant,
                    nsu=doc.nsu,
                    schema=doc.schema,
                    document_type=doc_type,
                    xml=doc.xml,
                    processing_status=DFeDistributionDocument.PROCESSING_PENDING,
                )
                saved += 1
        except IntegrityError:
            logger.debug(f"Documento NSU={doc.nsu} inserido concorrentemente. Ignorando.")
    return saved


# ─────────────────────────────────────────────────────────────────────────────
# PROCESSAMENTO DOS DOCUMENTOS (SEPARADO DO DOWNLOAD)
# ─────────────────────────────────────────────────────────────────────────────

@shared_task
def process_pending_dfe_documents(account_id: str):
    """
    Processa documentos pendentes salvos pelo sync.
    Separado do download para que uma falha no processamento não afete o NSU.
    """
    from apps.accounts.models import Account
    account = Account.objects.get(id=account_id)

    pending_docs = DFeDistributionDocument.all_objects.filter(
        account=account,
        processing_status=DFeDistributionDocument.PROCESSING_PENDING,
    ).order_by('nsu')

    for doc in pending_docs:
        try:
            _process_single_document(doc)
        except Exception as e:
            logger.error(
                f"Erro ao processar doc NSU={doc.nsu} "
                f"(schema={doc.schema}): {e}"
            )
            doc.processing_status = DFeDistributionDocument.PROCESSING_ERROR
            doc.processing_error = str(e)[:2000]
            doc.processed_at = timezone.now()
            doc.save(update_fields=[
                'processing_status', 'processing_error', 'processed_at'
            ])


def _process_single_document(doc: DFeDistributionDocument):
    """Processa um único documento DF-e baseado no seu tipo."""

    if doc.document_type == DFeDistributionDocument.DOC_RES_NFE:
        _process_res_nfe(doc)

    elif doc.document_type == DFeDistributionDocument.DOC_PROC_NFE:
        _process_proc_nfe(doc)

    elif doc.document_type in (
        DFeDistributionDocument.DOC_RES_EVENTO,
        DFeDistributionDocument.DOC_PROC_EVENTO,
    ):
        # Eventos: logar e marcar como skipped por enquanto
        logger.info(
            f"Documento de evento NSU={doc.nsu} "
            f"(type={doc.document_type}). Skipping."
        )
        doc.processing_status = DFeDistributionDocument.PROCESSING_SKIPPED
        doc.processed_at = timezone.now()
        doc.save(update_fields=['processing_status', 'processed_at'])

    else:
        logger.warning(
            f"Documento de tipo desconhecido NSU={doc.nsu} "
            f"(schema={doc.schema}). Skipping."
        )
        doc.processing_status = DFeDistributionDocument.PROCESSING_SKIPPED
        doc.processed_at = timezone.now()
        doc.save(update_fields=['processing_status', 'processed_at'])


def _process_res_nfe(doc: DFeDistributionDocument):
    """
    Processa um resumo de NF-e (resNFe).
    Cria InboundNFe com status=summary e tenta manifestar Ciência da Operação.
    """
    parsed = parse_nfe_xml(doc.xml)

    # Extrair chave de acesso e salvar no doc para referência
    if parsed.access_key and not doc.access_key:
        doc.access_key = parsed.access_key

    # Idempotência: verificar se já temos essa nota
    existing = InboundNFe.all_objects.filter(
        account=doc.account,
        access_key=parsed.access_key
    ).first()

    if existing:
        # Nota já existe — verificar se precisa atualizar com dados do resumo
        logger.info(
            f"InboundNFe {parsed.access_key} já existe "
            f"(status={existing.status}). Pulando resNFe."
        )
    else:
        inv_created = InboundNFe.all_objects.create(
            account=doc.account,
            branch=doc.branch,
            restaurant=doc.restaurant,
            access_key=parsed.access_key,
            nsu=doc.nsu,
            number=parsed.number,
            series=parsed.series,
            issue_date=parsed.issue_date,
            supplier_cnpj=parsed.supplier_cnpj,
            supplier_name=parsed.supplier_name,
            total_products=parsed.total_products,
            total_invoice=parsed.total_invoice,
            status=InboundNFe.STATUS_SUMMARY,
            distribution_type=InboundNFe.DISTRIBUTION_SUMMARY,
            xml_status=InboundNFe.XML_STATUS_SUMMARY_ONLY,
            summary_xml=doc.xml,
        )
        try:
            from apps.inbound_nfe.services.notifications import notify_new_inbound_nfe
            notify_new_inbound_nfe(inv_created)
        except Exception as e:
            logger.error(f"Erro ao notificar resNFe: {e}")

    # Marcar documento como processado
    doc.processing_status = DFeDistributionDocument.PROCESSING_OK
    doc.processed_at = timezone.now()
    doc.save(update_fields=[
        'access_key', 'processing_status', 'processed_at'
    ])


def _process_proc_nfe(doc: DFeDistributionDocument):
    """
    Processa uma NF-e completa (procNFe).
    Cria ou atualiza InboundNFe com itens e tenta matching automático.
    """
    from apps.inbound_nfe.services.matching import apply_mapping_to_item

    parsed = parse_nfe_xml(doc.xml)

    # Salvar chave de acesso no documento
    if parsed.access_key and not doc.access_key:
        doc.access_key = parsed.access_key

    # Buscar ou criar InboundNFe
    invoice, created = InboundNFe.all_objects.get_or_create(
        account=doc.account,
        access_key=parsed.access_key,
        defaults={
            'branch': doc.branch,
            'restaurant': doc.restaurant,
            'nsu': doc.nsu,
            'number': parsed.number,
            'series': parsed.series,
            'issue_date': parsed.issue_date,
            'supplier_cnpj': parsed.supplier_cnpj,
            'supplier_name': parsed.supplier_name,
            'total_products': parsed.total_products,
            'total_invoice': parsed.total_invoice,
            'status': InboundNFe.STATUS_PENDING_MAPPING,
            'distribution_type': InboundNFe.DISTRIBUTION_FULL,
            'xml_status': InboundNFe.XML_STATUS_FULL_XML_AVAILABLE,
            'full_xml': doc.xml,
        }
    )

    if created:
        try:
            from apps.inbound_nfe.services.notifications import notify_new_inbound_nfe
            notify_new_inbound_nfe(invoice)
        except Exception as e:
            logger.error(f"Erro ao notificar procNFe: {e}")

    if not created:
        # Atualizar com dados completos (pode ter vindo do resNFe antes)
        invoice.number = parsed.number or invoice.number
        invoice.series = parsed.series or invoice.series
        invoice.issue_date = parsed.issue_date or invoice.issue_date
        invoice.supplier_cnpj = parsed.supplier_cnpj or invoice.supplier_cnpj
        invoice.supplier_name = parsed.supplier_name or invoice.supplier_name
        invoice.total_products = parsed.total_products or invoice.total_products
        invoice.total_invoice = parsed.total_invoice or invoice.total_invoice
        invoice.distribution_type = InboundNFe.DISTRIBUTION_FULL
        invoice.xml_status = InboundNFe.XML_STATUS_FULL_XML_AVAILABLE
        invoice.full_xml = doc.xml
        if doc.nsu:
            try:
                if not invoice.nsu or int(doc.nsu) > int(invoice.nsu):
                    invoice.nsu = doc.nsu
            except (ValueError, TypeError):
                invoice.nsu = doc.nsu
        if invoice.status == InboundNFe.STATUS_SUMMARY:
            invoice.status = InboundNFe.STATUS_PENDING_MAPPING
        invoice.save()

    # Criar itens se ainda não existem
    if parsed.items:
        existing_item_numbers = set(
            InboundNFeItem.all_objects.filter(invoice=invoice).values_list("item_number", flat=True)
        )
        for p_item in parsed.items:
            if p_item.item_number in existing_item_numbers:
                continue
            item = InboundNFeItem.all_objects.create(
                account=doc.account,
                branch=doc.branch,
                restaurant=doc.restaurant,
                invoice=invoice,
                item_number=p_item.item_number,
                supplier_code=p_item.supplier_code,
                ean=p_item.ean,
                description=p_item.description,
                ncm=p_item.ncm,
                cfop=p_item.cfop,
                commercial_unit=p_item.commercial_unit,
                commercial_quantity=p_item.commercial_quantity,
                commercial_unit_value=p_item.commercial_unit_value,
                taxable_unit=p_item.taxable_unit,
                taxable_quantity=p_item.taxable_quantity,
                taxable_unit_value=p_item.taxable_unit_value,
                product_total=p_item.product_total,
                discount=p_item.discount,
                freight=p_item.freight,
                insurance=p_item.insurance,
                other_expenses=p_item.other_expenses,
                ean_trib=p_item.ean_trib,
                cest=p_item.cest,
                tax_data=p_item.tax_data,
            )

            # Tentar matching automático (EAN/GTIN, SupplierMapping)
            try:
                apply_mapping_to_item(item, invoice.supplier_cnpj)
            except Exception as e:
                logger.warning(
                    f"Matching falhou para item {item.description}: {e}"
                )

        # Verificar se todos os itens foram mapeados automaticamente
        items_qs = InboundNFeItem.all_objects.filter(invoice=invoice)
        if items_qs.exists() and not items_qs.filter(ingredient__isnull=True, product__isnull=True).exists():
            invoice.status = InboundNFe.STATUS_PENDING_RECEIPT
        else:
            invoice.status = InboundNFe.STATUS_PENDING_MAPPING
        invoice.save(update_fields=['status'])

    # Marcar documento como processado com sucesso
    doc.access_key = parsed.access_key or doc.access_key
    doc.processing_status = DFeDistributionDocument.PROCESSING_OK
    doc.processing_error = ""
    doc.processed_at = timezone.now()
    doc.save(update_fields=[
        'access_key', 'processing_status', 'processed_at', 'processing_error'
    ])


@shared_task(bind=True, max_retries=5, default_retry_delay=45)
def fetch_full_xml_task(self, invoice_id: str):
    """
    Tarefa em segundo plano para buscar o XML completo (procNFe) via consChNFe
    após o registro da Ciência da Operação.
    """
    from apps.inbound_nfe.models import InboundNFe
    from apps.inbound_nfe.services.manifestation import fetch_full_xml

    try:
        invoice = InboundNFe.all_objects.filter(id=invoice_id).first()
        if not invoice:
            logger.warning(f"fetch_full_xml_task: NF-e {invoice_id} não encontrada.")
            return

        if invoice.xml_status == InboundNFe.XML_STATUS_FULL_XML_AVAILABLE:
            logger.info(f"fetch_full_xml_task: NF-e {invoice.access_key} já possui XML completo.")
            return

        success = fetch_full_xml(invoice)
        if not success:
            logger.info(
                f"fetch_full_xml_task: procNFe ainda não liberado pela SEFAZ para "
                f"{invoice.access_key}. Tentativa {self.request.retries + 1}/5."
            )
            raise self.retry(countdown=45 * (2 ** self.request.retries))
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=45 * (2 ** self.request.retries))
        logger.error(f"fetch_full_xml_task: Falha definitiva ao obter procNFe para {invoice_id}: {exc}")
