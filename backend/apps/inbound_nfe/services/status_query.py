"""
Serviço para consulta de situação de NF-e diretamente na SEFAZ (NfeConsultaProtocolo4).
Permite verificar em tempo real se uma nota foi cancelada, denegada ou autorizada,
e reconciliar notas previamente importadas.
"""

import logging
from typing import Dict, Any
from datetime import datetime
import requests
import urllib3
import xml.etree.ElementTree as ET
from django.utils import timezone

from apps.inbound_nfe.models import InboundNFe
from apps.inbound_nfe.services.certificate import get_certificate_paths, cleanup_temp_files
from apps.inbound_nfe.services.cancellation import apply_cancellation

logger = logging.getLogger(__name__)

# Suprimir avisos de SSL em consultas SEFAZ que utilizam AC Raiz Brasileira
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Tabela de WebServices de Consulta de Situação por UF / Autorizador
URLS_CONSULTA = {
    # SVRS: AC, AL, AP, CE, DF, ES, PA, PB, PI, RJ, RN, RO, RR, SC, SE, TO
    "SVRS": {
        "production": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "homologation": "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
    },
    # SP
    "35": {
        "production": "https://nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx",
        "homologation": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx",
    },
    # MG
    "31": {
        "production": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeConsultaProtocolo4",
        "homologation": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeConsultaProtocolo4",
    },
    # PR
    "41": {
        "production": "https://nfe.fazenda.pr.gov.br/nfe/NFeConsultaProtocolo4",
        "homologation": "https://homologacao.nfe.fazenda.pr.gov.br/nfe/NFeConsultaProtocolo4",
    },
    # RS
    "43": {
        "production": "https://nfe.sefaz.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "homologation": "https://nfe-homologacao.sefaz.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
    },
    # BA
    "29": {
        "production": "https://nfe.sefaz.ba.gov.br/webservices/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx",
        "homologation": "https://hnfe.sefaz.ba.gov.br/webservices/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx",
    },
    # GO
    "52": {
        "production": "https://nfe.sefaz.go.gov.br/nfe/services/NFeConsultaProtocolo4",
        "homologation": "https://homolog.sefaz.go.gov.br/nfe/services/NFeConsultaProtocolo4",
    },
    # MS
    "50": {
        "production": "https://nfe.sefaz.ms.gov.br/ws/NFeConsultaProtocolo4",
        "homologation": "https://hom.nfe.sefaz.ms.gov.br/ws/NFeConsultaProtocolo4",
    },
    # MT
    "51": {
        "production": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeConsulta4",
        "homologation": "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeConsulta4",
    },
    # AM
    "13": {
        "production": "https://nfe.sefaz.am.gov.br/services2/services/NfeConsulta4",
        "homologation": "https://homnfe.sefaz.am.gov.br/services2/services/NfeConsulta4",
    },
    # SVAN: MA
    "21": {
        "production": "https://www.sefazvirtual.fazenda.gov.br/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx",
        "homologation": "https://hom.sefazvirtual.fazenda.gov.br/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx",
    },
}


def get_consulta_url(access_key: str, environment: str = "production") -> str:
    """Resolve a URL correta do webservice de consulta da SEFAZ com base no código da UF da chave."""
    uf_code = access_key[:2] if access_key and len(access_key) >= 2 else ""
    env = "homologation" if environment == "homologation" else "production"

    if uf_code in URLS_CONSULTA:
        return URLS_CONSULTA[uf_code][env]
    return URLS_CONSULTA["SVRS"][env]


def _build_cons_sit_xml(access_key: str, environment: str = "production") -> str:
    is_prod = str(environment) in ("1", "production")
    tp_amb = "1" if is_prod else "2"
    # A SEFAZ rejeita com cStat 588 se houver quebras de linha ou espaçamentos entre as tags do consSitNFe
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        f'<soap12:Body>'
        f'<nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsultaProtocolo4">'
        f'<consSitNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<xServ>CONSULTAR</xServ>'
        f'<chNFe>{access_key}</chNFe>'
        f'</consSitNFe>'
        f'</nfeDadosMsg>'
        f'</soap12:Body>'
        f'</soap12:Envelope>'
    )


def query_nfe_status_sefaz(invoice: InboundNFe, actor=None) -> Dict[str, Any]:
    """
    Envia consSitNFe para a SEFAZ do autorizador da chave.
    Interpreta o retorno (retConsSitNFe):
    - 100: Autorizada
    - 101, 151: Cancelamento Homologado
    - 110, 301, 302: Uso Denegado
    Se for cancelada, chama apply_cancellation automaticamente.
    """
    access_key = invoice.access_key
    if not access_key or len(access_key) != 44:
        raise ValueError(f"Chave de acesso inválida para consulta: '{access_key}'")

    from apps.invoices.models import FiscalConfig
    config = None
    if invoice.restaurant_id:
        config = FiscalConfig.all_objects.filter(restaurant_id=invoice.restaurant_id).first()
    if not config and invoice.account_id:
        config = FiscalConfig.all_objects.filter(account_id=invoice.account_id).first()

    raw_env = config.environment if config and config.environment else "1"
    is_prod = str(raw_env) in ("1", "production")
    environment = "production" if is_prod else "homologation"

    url = get_consulta_url(access_key, environment=environment)
    payload = _build_cons_sit_xml(access_key, environment=environment)

    cert_paths = None
    try:
        cert_paths = get_certificate_paths(invoice.account, restaurant_id=invoice.restaurant_id)
        cert_path, key_path = cert_paths

        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
        }

        logger.info(f"Consultando situação da NF-e {access_key} na SEFAZ ({url})")
        response = requests.post(
            url,
            data=payload.encode("utf-8"),
            headers=headers,
            cert=(cert_path, key_path),
            verify=False,
            timeout=30,
        )
        response.raise_for_status()
        response_xml = response.text

    except Exception as exc:
        logger.error(f"Erro ao consultar situação da NF-e {access_key} na SEFAZ: {exc}")
        invoice.last_status_check_at = timezone.now()
        invoice.last_status_reason = f"Falha na comunicação com a SEFAZ: {exc}"
        invoice.save(update_fields=["last_status_check_at", "last_status_reason"])
        return {
            "success": False,
            "error": str(exc),
            "fiscal_status": invoice.fiscal_status,
        }
    finally:
        if cert_paths:
            cleanup_temp_files(cert_paths[0], cert_paths[1])

    return parse_and_apply_cons_sit_response(invoice, response_xml, actor=actor)


def parse_and_apply_cons_sit_response(invoice: InboundNFe, response_xml: str, actor=None) -> Dict[str, Any]:
    """Interpreta retConsSitNFe e atualiza a InboundNFe."""
    try:
        root = ET.fromstring(response_xml)
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro no parser XML do retorno da SEFAZ: {e}",
            "fiscal_status": invoice.fiscal_status,
        }

    # Extrair cStat principal do retConsSitNFe
    cstat = ""
    reason = ""
    dh_recbto_str = ""
    n_prot = ""

    # Percorre para localizar retConsSitNFe
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "retConsSitNFe":
            for child in elem:
                ctag = child.tag.split("}")[-1]
                if ctag == "cStat":
                    cstat = (child.text or "").strip()
                elif ctag == "xMotivo":
                    reason = (child.text or "").strip()
                elif ctag == "dhRecbto":
                    dh_recbto_str = (child.text or "").strip()
                elif ctag == "nProt" and not n_prot:
                    n_prot = (child.text or "").strip()
                elif ctag == "protNFe":
                    for pchild in child.iter():
                        ptag = pchild.tag.split("}")[-1]
                        if ptag == "nProt" and not n_prot:
                            n_prot = (pchild.text or "").strip()

    # Se não achou na busca específica, busca genérica
    if not cstat:
        for elem in root.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "cStat" and not cstat:
                cstat = (elem.text or "").strip()
            elif tag == "xMotivo" and not reason:
                reason = (elem.text or "").strip()
            elif tag == "nProt" and not n_prot:
                n_prot = (elem.text or "").strip()
            elif tag in ("dhRecbto", "dhRegEvento") and not dh_recbto_str:
                dh_recbto_str = (elem.text or "").strip()

    # Verificar se há evento de cancelamento incorporado na resposta (procEventoNFe ou retEvento)
    cancellation_prot = ""
    cancellation_reason = ""
    cancellation_dt_str = ""

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "infEvento":
            tp_evento = ""
            current_prot = ""
            current_just = ""
            current_dh = ""
            for sub in elem.iter():
                subtag = sub.tag.split("}")[-1]
                if subtag == "tpEvento":
                    tp_evento = (sub.text or "").strip()
                elif subtag == "nProt":
                    current_prot = (sub.text or "").strip()
                elif subtag in ("xJust", "xMotivo"):
                    current_just = (sub.text or "").strip()
                elif subtag in ("dhEvento", "dhRegEvento"):
                    current_dh = (sub.text or "").strip()

            if tp_evento == "110111":
                cancellation_prot = current_prot or cancellation_prot
                cancellation_reason = current_just or cancellation_reason
                cancellation_dt_str = current_dh or cancellation_dt_str

    event_dt = None
    target_dt_str = cancellation_dt_str or dh_recbto_str
    if target_dt_str:
        try:
            event_dt = datetime.fromisoformat(target_dt_str)
        except Exception:
            event_dt = None

    now = timezone.now()
    invoice.last_status_check_at = now
    invoice.last_status_cstat = cstat
    invoice.last_status_reason = reason

    is_cancelled = cstat in ("101", "151") or bool(cancellation_prot)
    is_authorized = cstat == "100" and not is_cancelled
    is_denied = cstat in ("110", "301", "302")

    cancellation_result = None

    if is_cancelled:
        logger.warning(
            f"SEFAZ confirmou CANCELAMENTO da NF-e {invoice.access_key} (cStat={cstat}, {reason})"
        )
        cancellation_result = apply_cancellation(
            invoice=invoice,
            protocol=cancellation_prot or n_prot,
            reason=cancellation_reason or reason,
            event_datetime=event_dt or now,
            actor=actor,
        )
        invoice.refresh_from_db()

    elif is_authorized:
        invoice.fiscal_status = InboundNFe.FISCAL_AUTHORIZED
        invoice.save(update_fields=["fiscal_status", "last_status_check_at", "last_status_cstat", "last_status_reason"])

    elif is_denied:
        invoice.fiscal_status = InboundNFe.FISCAL_DENIED
        invoice.save(update_fields=["fiscal_status", "last_status_check_at", "last_status_cstat", "last_status_reason"])

    else:
        invoice.save(update_fields=["last_status_check_at", "last_status_cstat", "last_status_reason"])

    return {
        "success": True,
        "cstat": cstat,
        "reason": reason,
        "protocol": cancellation_prot or n_prot,
        "fiscal_status": invoice.fiscal_status,
        "is_cancelled": is_cancelled,
        "is_authorized": is_authorized,
        "cancellation_result": cancellation_result,
        "raw_response": response_xml[:1000],
    }
