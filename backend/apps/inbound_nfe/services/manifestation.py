import datetime
import logging
import re
from dataclasses import dataclass
from typing import Optional
import requests
import xml.etree.ElementTree as ET
from django.utils import timezone

from apps.inbound_nfe.services.certificate import (
    get_certificate_objects,
    get_certificate_paths,
    cleanup_temp_files,
)
from apps.inbound_nfe.services.signer import (
    sign_xml_node,
    validate_no_forbidden_prefixes,
    verify_xml_signature,
    NFE_NS,
    XMLDSIG_NS,
)

logger = logging.getLogger(__name__)

EVENT_CONFIG = {
    'science': {
        'code': '210210',
        'desc': 'Ciencia da Operacao',
    },
    'confirm': {
        'code': '210200',
        'desc': 'Confirmacao da Operacao',
    },
    'unknown': {
        'code': '210220',
        'desc': 'Desconhecimento da Operacao',
    },
    'not_performed': {
        'code': '210240',
        'desc': 'Operacao nao Realizada',
    },
}

WEBSERVICE_URLS = {
    'production': 'https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx',
    'homologation': 'https://hom.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx',
}


@dataclass
class ManifestationResponse:
    """Objeto estruturado com a resposta da SEFAZ para eventos de manifestação."""
    batch_cstat: str
    batch_reason: str
    event_cstat: Optional[str] = None
    event_reason: Optional[str] = None
    protocol: Optional[str] = None
    registered_at: Optional[datetime.datetime] = None
    raw_xml: str = ""
    request_xml: str = ""

    def __iter__(self):
        """Permite desempacotamento retrocompatível como: cstat, reason, dh = response."""
        cstat = self.event_cstat or self.batch_cstat
        reason = self.event_reason or self.batch_reason
        dh = self.registered_at or datetime.datetime.now()
        return iter((cstat, reason, dh))

    @property
    def is_success(self) -> bool:
        # 135: Evento registrado e vinculado
        # 136: Evento registrado, mas não vinculado
        # 573: Duplicidade de evento (já registrado)
        return self.event_cstat in ("135", "136", "573")


def build_event_xml(
    cnpj: str,
    access_key: str,
    event_type: str,
    environment: str = "production",
    reason: str = "",
    seq: int = 1,
) -> tuple[str, str]:
    """
    Constrói a estrutura XML do envEvento para manifestação do destinatário.
    Utiliza namespace padrão da NF-e sem prefixos (xmlns="http://www.portalfiscal.inf.br/nfe").
    Retorna (xml_text, reference_id).
    """
    if event_type not in EVENT_CONFIG:
        raise ValueError(f"Tipo de evento inválido: {event_type}")

    if event_type == 'not_performed' and len((reason or "").strip()) < 15:
        raise ValueError(
            "Para 'Operação Não Realizada', a justificativa deve ter no mínimo 15 caracteres."
        )

    ev_info = EVENT_CONFIG[event_type]
    tp_evento = ev_info['code']
    desc_evento = ev_info['desc']
    tp_amb = "1" if environment == "production" else "2"
    ref_id = f"ID{tp_evento}{access_key}{seq:02d}"

    # Data/hora no formato ISO com fuso horário (ex: 2026-09-02T16:00:00-03:00)
    now_str = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    if len(now_str) > 2 and (now_str[-2:].isdigit() and now_str[-5] in ('+', '-')):
        now_str = now_str[:-2] + ":" + now_str[-2:]

    just_tag = f"<xJust>{reason.strip()}</xJust>" if event_type == 'not_performed' else ""

    xml_text = (
        f'<envEvento xmlns="{NFE_NS}" versao="1.00">'
        f'<idLote>1</idLote>'
        f'<evento versao="1.00">'
        f'<infEvento Id="{ref_id}">'
        f'<cOrgao>91</cOrgao>'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<CNPJ>{cnpj}</CNPJ>'
        f'<chNFe>{access_key}</chNFe>'
        f'<dhEvento>{now_str}</dhEvento>'
        f'<tpEvento>{tp_evento}</tpEvento>'
        f'<nSeqEvento>{seq}</nSeqEvento>'
        f'<verEvento>1.00</verEvento>'
        f'<detEvento versao="1.00">'
        f'<descEvento>{desc_evento}</descEvento>'
        f'{just_tag}'
        f'</detEvento>'
        f'</infEvento>'
        f'</evento>'
        f'</envEvento>'
    )
    return xml_text, ref_id


def build_soap_envelope(signed_env_evento_xml: str) -> str:
    """Monta o envelope SOAP 1.2 com o envEvento assinado dentro de nfeDadosMsg."""
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        f'xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        f'<soap12:Body>'
        f'<nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">'
        f'{signed_env_evento_xml}'
        f'</nfeDadosMsg>'
        f'</soap12:Body>'
        f'</soap12:Envelope>'
    )


def manifest_nfe(
    account,
    cnpj: str,
    access_key: str,
    event_type: str,
    uf_code: str = "35",
    reason: str = "",
    environment: str = "production",
    restaurant_id=None,
    seq: int = 1,
) -> ManifestationResponse:
    """
    Executa a manifestação do destinatário oficial na SEFAZ:
    1. Monta o XML do evento (envEvento) em namespace padrão sem prefixo
    2. Assina digitalmente o nó <infEvento> via XMLDSig com certificado A1 sem prefixo ds:
    3. Valida a ausência de prefixos proibidos (Rejeição 404)
    4. Valida a assinatura localmente antes do envio (Rejeição 297)
    5. Transmite via SOAP 1.2 mTLS para o webservice NFeRecepcaoEvento4 da SEFAZ AN
    6. Analisa cStat do lote e do evento individual
    """
    clean_cnpj = re.sub(r'\D', '', cnpj or '')
    if not clean_cnpj:
        raise ValueError("CNPJ não informado para manifestação.")

    # 1. Carregar certificado e chave em memória para assinatura
    private_key, certificate, _ = get_certificate_objects(account, restaurant_id=restaurant_id)
    if not private_key or not certificate:
        raise ValueError("Chave privada ou certificado não encontrados no A1.")

    # 2. Construir XML do evento e assinar
    xml_str, ref_id = build_event_xml(
        cnpj=clean_cnpj,
        access_key=access_key,
        event_type=event_type,
        environment=environment,
        reason=reason,
        seq=seq,
    )

    # Log técnico do XML antes da assinatura
    logger.info(f"--- XML ANTES DA ASSINATURA ---\n{xml_str}")

    signed_xml_str = sign_xml_node(
        xml_str,
        target_node_tag='infEvento',
        reference_id=ref_id,
        private_key=private_key,
        certificate=certificate,
    )

    # Validar que NÃO há prefixos proibidos pela SEFAZ (ns0:, ds:, nfe:, etc.)
    validate_no_forbidden_prefixes(signed_xml_str)

    # Verificação criptográfica local obrigatória antes de qualquer chamada à SEFAZ
    verify_xml_signature(signed_xml_str)
    logger.info("Verificação local da assinatura XMLDSig: VÁLIDA (OK).")

    # Log técnico do XML assinado
    logger.info(f"--- XML DEPOIS DA ASSINATURA ---\n{signed_xml_str}")

    soap_payload = build_soap_envelope(signed_xml_str)

    # Log técnico do SOAP enviado
    logger.info(f"--- SOAP ENVIADO ---\n{soap_payload}")

    # 3. Transmissão SOAP com mTLS
    cert_paths = None
    try:
        cert_paths = get_certificate_paths(account, restaurant_id=restaurant_id)
        cert_path, key_path = cert_paths

        url = WEBSERVICE_URLS.get(environment, WEBSERVICE_URLS['production'])
        headers = {
            'Content-Type': 'application/soap+xml; charset=utf-8',
        }

        logger.info(
            f"SEFAZ RecepcaoEvento: event={event_type} ({EVENT_CONFIG[event_type]['code']}), "
            f"chNFe={access_key}, cnpj={clean_cnpj}, env={environment}"
        )

        response = requests.post(
            url,
            data=soap_payload.encode('utf-8'),
            headers=headers,
            cert=(cert_path, key_path),
            timeout=30,
        )
        response.raise_for_status()

        return parse_event_response(response.text, request_xml=signed_xml_str)

    finally:
        if cert_paths:
            cleanup_temp_files(*cert_paths)


def parse_event_response(xml_text: str, request_xml: str = "") -> ManifestationResponse:
    """
    Analisa o retorno da SEFAZ para RecepcaoEvento, extraindo o status do lote
    e o status do evento individual.
    """
    try:
        root = ET.fromstring(xml_text.strip())
    except Exception:
        clean_text = xml_text.strip()
        if clean_text.startswith("<?xml"):
            clean_text = clean_text[clean_text.find("?>") + 2:].strip()
        root = ET.fromstring(clean_text)

    namespaces = {
        'soap': 'http://www.w3.org/2003/05/soap-envelope',
        'nfe': 'http://www.portalfiscal.inf.br/nfe',
    }

    # Status geral do lote (retEnvEvento)
    cstat_lote_el = root.find('.//nfe:cStat', namespaces)
    reason_lote_el = root.find('.//nfe:xMotivo', namespaces)
    batch_cstat = cstat_lote_el.text if cstat_lote_el is not None else "999"
    batch_reason = reason_lote_el.text if reason_lote_el is not None else "Erro desconhecido na resposta SEFAZ"

    # Status do evento individual (retEvento/infEvento)
    ret_inf = root.find('.//nfe:retEvento/nfe:infEvento', namespaces)
    event_cstat = None
    event_reason = None
    protocol = None
    registered_at = None

    if ret_inf is not None:
        cstat_el = ret_inf.find('nfe:cStat', namespaces)
        reason_el = ret_inf.find('nfe:xMotivo', namespaces)
        prot_el = ret_inf.find('nfe:nProt', namespaces)
        dh_el = ret_inf.find('nfe:dhRegEvento', namespaces)

        event_cstat = cstat_el.text if cstat_el is not None else None
        event_reason = reason_el.text if reason_el is not None else None
        protocol = prot_el.text if prot_el is not None else None

        if dh_el is not None and dh_el.text:
            try:
                registered_at = datetime.datetime.fromisoformat(dh_el.text)
            except Exception:
                registered_at = timezone.now()

    logger.info(
        f"SEFAZ RecepcaoEvento retorno: lote_cStat={batch_cstat}, "
        f"evento_cStat={event_cstat}, xMotivo={event_reason or batch_reason}, prot={protocol}"
    )

    return ManifestationResponse(
        batch_cstat=batch_cstat,
        batch_reason=batch_reason,
        event_cstat=event_cstat,
        event_reason=event_reason,
        protocol=protocol,
        registered_at=registered_at,
        raw_xml=xml_text,
        request_xml=request_xml,
    )


def register_science(invoice, user=None) -> tuple[bool, str]:
    """
    Executa a Ciência da Operação (210210) de forma oficial e controlada:
    1. Verifica idempotência (se já aceito, não reenvia evento).
    2. Registra a NFeManifestation como PENDING.
    3. Assina e transmite à SEFAZ via NFeRecepcaoEvento4.
    4. Interpreta lote e evento individual (sucesso = 135 ou 573).
    5. Se aceito, atualiza a NF-e para science_registered e full_xml_pending.
    6. Executa a busca imediata do procNFe via consChNFe. Se ainda não disponível, enfileira retry.
    """
    from apps.invoices.models import FiscalConfig
    from apps.inbound_nfe.models import NFeManifestation, InboundNFe

    if not invoice or not invoice.access_key:
        return False, "Chave de acesso inválida."

    # 1. Idempotência: verificar se evento 210210 já foi aceito anteriormente
    existing = NFeManifestation.all_objects.filter(
        invoice=invoice,
        event_code="210210",
        status=NFeManifestation.STATUS_ACCEPTED,
    ).first()

    if existing:
        logger.info(
            f"NF-e {invoice.access_key} já possui Ciência da Operação aceita "
            f"(protocolo: {existing.protocol}). Buscando XML completo..."
        )
        invoice.manifestation_status = InboundNFe.MANIFEST_SCIENCE_REGISTERED
        invoice.save(update_fields=['manifestation_status'])

        # Tentar obter XML completo se ainda não estiver disponível
        if invoice.xml_status != InboundNFe.XML_STATUS_FULL_XML_AVAILABLE:
            fetched = fetch_full_xml(invoice)
            if fetched:
                return True, f"Ciência já registrada anteriormente (Prot: {existing.protocol}). XML completo obtido com sucesso!"
            else:
                return True, f"Ciência já registrada (Prot: {existing.protocol}). Aguardando processamento do XML completo pela SEFAZ."
        return True, f"Ciência já registrada e XML completo já disponível."

    # 2. Obter configurações fiscais do restaurante
    config = FiscalConfig.all_objects.filter(account=invoice.account)
    if invoice.restaurant_id:
        config_obj = config.filter(restaurant_id=invoice.restaurant_id).first() or config.first()
    else:
        config_obj = config.first()

    cnpj = (
        (config_obj.cnpj if config_obj else '')
        or (config_obj.certificate_cnpj if config_obj else '')
        or getattr(invoice.account, 'cnpj', '')
    )
    clean_cnpj = re.sub(r'\D', '', cnpj or '')
    if not clean_cnpj:
        return False, "CNPJ não configurado no perfil fiscal para manifestação."

    environment = "production"
    if config_obj and config_obj.environment == FiscalConfig.ENV_HOMOLOGATION:
        environment = "homologation"

    # 3. Localizar ou criar registro NFeManifestation com sequence=1 (preservando histórico de tentativas)
    manifestation = NFeManifestation.all_objects.filter(
        invoice=invoice,
        event_code="210210",
        sequence=1,
    ).first()

    if manifestation:
        # Se já existia tentativa anterior (ex: rejeição 404), arquiva no histórico para auditoria
        prev_attempt = {
            "attempt_at": timezone.now().isoformat(),
            "status": manifestation.status,
            "sefaz_batch_status": manifestation.sefaz_batch_status,
            "sefaz_batch_reason": manifestation.sefaz_batch_reason,
            "sefaz_event_status": manifestation.sefaz_event_status,
            "sefaz_event_reason": manifestation.sefaz_event_reason,
            "protocol": manifestation.protocol,
            "request_xml": manifestation.request_xml,
            "response_xml": manifestation.response_xml,
        }
        history = list(manifestation.history or [])
        history.append(prev_attempt)
        manifestation.history = history
        manifestation.status = NFeManifestation.STATUS_PENDING
        manifestation.event_datetime = timezone.now()
        manifestation.save()
    else:
        manifestation = NFeManifestation.all_objects.create(
            account=invoice.account,
            branch=invoice.branch,
            restaurant=invoice.restaurant,
            invoice=invoice,
            access_key=invoice.access_key,
            event_type=NFeManifestation.EVENT_SCIENCE,
            event_code="210210",
            sequence=1,
            event_datetime=timezone.now(),
            status=NFeManifestation.STATUS_PENDING,
        )

    try:
        resp = manifest_nfe(
            account=invoice.account,
            cnpj=clean_cnpj,
            access_key=invoice.access_key,
            event_type='science',
            environment=environment,
            restaurant_id=invoice.restaurant_id,
        )

        manifestation.sefaz_batch_status = resp.batch_cstat
        manifestation.sefaz_batch_reason = resp.batch_reason
        manifestation.sefaz_event_status = resp.event_cstat or ""
        manifestation.sefaz_event_reason = resp.event_reason or ""
        manifestation.protocol = resp.protocol or ""
        manifestation.request_xml = resp.request_xml
        manifestation.response_xml = resp.raw_xml
        manifestation.registered_at = resp.registered_at or timezone.now()

        if resp.is_success:
            manifestation.status = NFeManifestation.STATUS_ACCEPTED
            manifestation.save()

            invoice.manifestation_status = InboundNFe.MANIFEST_SCIENCE_REGISTERED
            invoice.xml_status = InboundNFe.XML_STATUS_FULL_XML_PENDING
            invoice.save(update_fields=['manifestation_status', 'xml_status'])

            # 4. Tentar buscar imediatamente o procNFe via consChNFe
            logger.info(f"Ciência aceita pela SEFAZ. Buscando XML completo (procNFe) para {invoice.access_key}...")
            fetched = fetch_full_xml(invoice)
            if fetched:
                return True, f"Ciência da Operação registrada (Prot: {manifestation.protocol}). XML completo obtido com sucesso!"

            # Se ainda não estiver pronto na SEFAZ, enfileirar tarefa Celery para download automático
            try:
                from apps.inbound_nfe.tasks import fetch_full_xml_task
                fetch_full_xml_task.delay(str(invoice.id))
            except Exception as exc:
                logger.warning(f"Não foi possível enfileirar fetch_full_xml_task: {exc}")

            return True, f"Ciência da Operação registrada (Prot: {manifestation.protocol}). Aguardando liberação do XML pela SEFAZ."

        else:
            manifestation.status = NFeManifestation.STATUS_REJECTED
            manifestation.save()

            invoice.manifestation_status = InboundNFe.MANIFEST_ERROR
            invoice.save(update_fields=['manifestation_status'])

            err_msg = resp.event_reason or resp.batch_reason or "Rejeição desconhecida na SEFAZ."
            cstat_code = resp.event_cstat or resp.batch_cstat
            return False, f"Rejeição SEFAZ ({cstat_code}): {err_msg}"

    except Exception as e:
        manifestation.status = NFeManifestation.STATUS_ERROR
        manifestation.sefaz_event_reason = str(e)
        manifestation.save()
        logger.error(f"Erro ao registrar ciência para {invoice.access_key}: {e}", exc_info=True)
        return False, f"Erro ao comunicar com a SEFAZ: {str(e)}"


def fetch_full_xml(invoice) -> bool:
    """
    Consulta a SEFAZ diretamente pela chave de acesso via consChNFe.
    Se o procNFe estiver disponível:
      - Salva o DFeDistributionDocument
      - Parseia e atualiza a MESMA InboundNFe
      - Cria os itens InboundNFeItem
      - Aplica o matching automático com o catálogo
      - Marca xml_status = full_xml_available
      - Retorna True
    Se ainda retornar apenas resNFe ou nenhum doc completo:
      - Mantém xml_status = full_xml_pending
      - Retorna False (para retry)
    """
    from apps.invoices.models import FiscalConfig
    from apps.inbound_nfe.models import InboundNFe, InboundNFeItem, DFeDistributionDocument
    from apps.inbound_nfe.services.sefaz_client import NFeDistribuicaoClient
    from apps.inbound_nfe.services.xml_parser import parse_nfe_xml
    from apps.inbound_nfe.services.matching import apply_mapping_to_item
    from apps.inbound_nfe.tasks import _resolve_uf_code

    if not invoice or not invoice.access_key:
        return False

    config = FiscalConfig.all_objects.filter(account=invoice.account)
    if invoice.restaurant_id:
        config_obj = config.filter(restaurant_id=invoice.restaurant_id).first() or config.first()
    else:
        config_obj = config.first()

    cnpj = (
        (config_obj.cnpj if config_obj else '')
        or (config_obj.certificate_cnpj if config_obj else '')
        or getattr(invoice.account, 'cnpj', '')
    )
    clean_cnpj = re.sub(r'\D', '', cnpj or '')
    if not clean_cnpj:
        logger.error(f"fetch_full_xml: CNPJ não encontrado para {invoice.access_key}")
        return False

    uf_code = _resolve_uf_code(config_obj.uf if config_obj else "RJ")
    environment = "production"
    if config_obj and config_obj.environment == FiscalConfig.ENV_HOMOLOGATION:
        environment = "homologation"

    client = NFeDistribuicaoClient(
        account=invoice.account,
        restaurant_id=invoice.restaurant_id,
        environment=environment,
    )

    try:
        resp = client.fetch_by_access_key(
            cnpj=clean_cnpj,
            uf_code=uf_code,
            access_key=invoice.access_key,
        )

        for doc in resp.documents:
            # Identificar procNFe completo
            is_proc_nfe = (
                doc.schema.startswith("procNFe")
                or "<nfeProc" in doc.xml
                or ("<infNFe" in doc.xml and "<det" in doc.xml)
            )

            if is_proc_nfe:
                logger.info(f"fetch_full_xml: procNFe recebido com sucesso para {invoice.access_key}!")
                
                # 1. Salvar ou atualizar DFeDistributionDocument
                target_nsu = doc.nsu or invoice.nsu
                dist_doc = None
                if target_nsu:
                    dist_doc = DFeDistributionDocument.all_objects.filter(
                        account=invoice.account,
                        nsu=target_nsu,
                    ).first()

                if not dist_doc and invoice.access_key:
                    dist_doc = DFeDistributionDocument.all_objects.filter(
                        account=invoice.account,
                        access_key=invoice.access_key,
                    ).first()

                if not dist_doc:
                    dist_doc = DFeDistributionDocument(
                        account=invoice.account,
                        restaurant=invoice.restaurant,
                        branch=invoice.branch,
                        access_key=invoice.access_key,
                        nsu=target_nsu or "CONS_CHAVE",
                    )

                dist_doc.schema = doc.schema or "procNFe_v4.00.xsd"
                dist_doc.xml = doc.xml
                dist_doc.document_type = DFeDistributionDocument.DOC_PROC_NFE
                dist_doc.processing_status = DFeDistributionDocument.PROCESSING_OK
                dist_doc.processed_at = timezone.now()
                dist_doc.save()

                # 2. Parsear XML completo
                parsed = parse_nfe_xml(doc.xml)

                # 3. Atualizar a mesma InboundNFe (NUNCA duplicar)
                invoice.number = parsed.number or invoice.number
                invoice.series = parsed.series or invoice.series
                invoice.issue_date = parsed.issue_date or invoice.issue_date
                invoice.supplier_cnpj = parsed.supplier_cnpj or invoice.supplier_cnpj
                invoice.supplier_name = parsed.supplier_name or invoice.supplier_name
                invoice.total_products = parsed.total_products or invoice.total_products
                invoice.total_invoice = parsed.total_invoice or invoice.total_invoice
                invoice.full_xml = doc.xml
                invoice.distribution_type = InboundNFe.DISTRIBUTION_FULL
                invoice.xml_status = InboundNFe.XML_STATUS_FULL_XML_AVAILABLE

                if invoice.status == InboundNFe.STATUS_SUMMARY:
                    invoice.status = InboundNFe.STATUS_PENDING_MAPPING
                invoice.save()

                # 4. Criar itens se o XML contiver <det>
                if parsed.items:
                    # Limpar itens anteriores para garantir consistência
                    InboundNFeItem.all_objects.filter(invoice=invoice).delete()

                    for p_item in parsed.items:
                        item = InboundNFeItem.all_objects.create(
                            account=invoice.account,
                            branch=invoice.branch,
                            restaurant=invoice.restaurant,
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

                        # Tentar matching automático
                        try:
                            apply_mapping_to_item(item, invoice.supplier_cnpj)
                        except Exception as m_err:
                            logger.warning(f"Matching falhou para item {item.description}: {m_err}")

                    # Se todos os itens foram mapeados automaticamente, marcar como pronta para entrada
                    items_qs = InboundNFeItem.all_objects.filter(invoice=invoice)
                    if items_qs.exists() and not items_qs.filter(ingredient__isnull=True, product__isnull=True).exists():
                        invoice.status = InboundNFe.STATUS_PENDING_RECEIPT
                    else:
                        invoice.status = InboundNFe.STATUS_PENDING_MAPPING
                    invoice.save(update_fields=['status'])

                # 5. Notificar gestores sobre a disponibilização do XML completo
                try:
                    from apps.inbound_nfe.services.notifications import notify_new_inbound_nfe
                    notify_new_inbound_nfe(invoice)
                except Exception as n_err:
                    logger.warning(f"Erro ao disparar notificação: {n_err}")

                return True

        # Se não retornou procNFe
        logger.info(f"fetch_full_xml: SEFAZ ainda não disponibilizou procNFe para {invoice.access_key} (docs={len(resp.documents)})")
        invoice.xml_status = InboundNFe.XML_STATUS_FULL_XML_PENDING
        invoice.save(update_fields=['xml_status'])
        return False

    except Exception as e:
        logger.error(f"Erro no fetch_full_xml para {invoice.access_key}: {e}", exc_info=True)
        return False


def confirm_science(invoice):
    """Atalho retrocompatível para Ciência da Operação (210210)."""
    ok, msg = register_science(invoice)
    return ("135" if ok else "999"), msg


def confirm_operation(invoice, user=None):
    """Atalho para Confirmação da Operação (210200), usado após conferência física/estoque."""
    from apps.invoices.models import FiscalConfig
    config = FiscalConfig.all_objects.filter(account=invoice.account)
    if invoice.restaurant_id:
        config_obj = config.filter(restaurant_id=invoice.restaurant_id).first() or config.first()
    else:
        config_obj = config.first()

    cnpj = (
        (config_obj.cnpj if config_obj else '')
        or (config_obj.certificate_cnpj if config_obj else '')
        or getattr(invoice.account, 'cnpj', '')
    )
    clean_cnpj = re.sub(r'\D', '', cnpj or '')
    environment = "production"
    if config_obj and config_obj.environment == FiscalConfig.ENV_HOMOLOGATION:
        environment = "homologation"

    resp = manifest_nfe(
        account=invoice.account,
        cnpj=clean_cnpj,
        access_key=invoice.access_key,
        event_type='confirm',
        environment=environment,
        restaurant_id=invoice.restaurant_id,
    )

    if resp.is_success:
        invoice.manifestation_status = 'confirmed'
        invoice.save(update_fields=['manifestation_status'])

    return resp.event_cstat or resp.batch_cstat, resp.event_reason or resp.batch_reason
