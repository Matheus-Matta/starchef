"""
Serviço para análise sintática (parser) de eventos fiscais da NF-e.
Suporta procEventoNFe (evento completo com assinatura e recibo) e resEvento (resumo do evento).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import xml.etree.ElementTree as ET


@dataclass
class ParsedNFeEvent:
    access_key: str
    event_code: str
    event_description: str
    sequence: int = 1
    event_datetime: Optional[datetime] = None
    protocol: str = ""
    sefaz_cstat: str = ""
    sefaz_reason: str = ""
    cancellation_reason: str = ""
    correction_text: str = ""
    raw_xml: str = ""

    @property
    def is_cancellation(self) -> bool:
        return self.event_code == "110111"

    @property
    def is_effective_cancellation(self) -> bool:
        """
        Retorna True se o evento for de cancelamento e estiver formalmente aceito pela SEFAZ.
        cStat 135: Evento registrado e vinculado a NF-e
        cStat 136: Evento registrado, mas não vinculado a NF-e
        cStat 155: Cancelamento de NF-e homologado fora de prazo
        Em resEvento a SEFAZ não envia cStat, mas a distribuição em si atesta a homologação.
        """
        if not self.is_cancellation:
            return False
        if not self.sefaz_cstat:
            return True
        return self.sefaz_cstat in ("135", "136", "155")


def _find_tag_text(root: ET.Element, tag_name: str) -> str:
    """Busca recursiva tolerante a namespaces para o valor textual de uma tag."""
    for elem in root.iter():
        local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local_name == tag_name:
            return (elem.text or "").strip()
    return ""


def _parse_iso_datetime(dt_str: str) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def parse_nfe_event(xml_content: str) -> ParsedNFeEvent:
    """
    Identifica se é procEventoNFe ou resEvento e extrai os dados estruturados do evento.
    """
    if not xml_content or not xml_content.strip():
        raise ValueError("Conteúdo XML vazio ao tentar processar evento da NF-e.")

    root = ET.fromstring(xml_content.strip())
    root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag

    if root_tag == "resEvento":
        return _parse_res_evento(root, xml_content)
    elif root_tag in ("procEventoNFe", "evento"):
        return _parse_proc_evento(root, xml_content)
    else:
        # Tenta verificar se contém infEvento internamente
        if any(elem.tag.endswith("infEvento") for elem in root.iter()):
            return _parse_proc_evento(root, xml_content)
        raise ValueError(f"XML não reconhecido como evento de NF-e (raiz: {root_tag})")


def _parse_res_evento(root: ET.Element, raw_xml: str) -> ParsedNFeEvent:
    access_key = _find_tag_text(root, "chNFe")
    event_code = _find_tag_text(root, "tpEvento")
    event_description = _find_tag_text(root, "xEvento")
    seq_str = _find_tag_text(root, "nSeqEvento")
    sequence = int(seq_str) if seq_str.isdigit() else 1

    dt_str = _find_tag_text(root, "dhEvento") or _find_tag_text(root, "dhRecbto")
    event_datetime = _parse_iso_datetime(dt_str)

    protocol = _find_tag_text(root, "nProt")

    return ParsedNFeEvent(
        access_key=access_key,
        event_code=event_code,
        event_description=event_description,
        sequence=sequence,
        event_datetime=event_datetime,
        protocol=protocol,
        sefaz_cstat="135",  # resEvento entregue pela SEFAZ indica homologação
        sefaz_reason=event_description,
        cancellation_reason="",
        correction_text="",
        raw_xml=raw_xml,
    )


def _parse_proc_evento(root: ET.Element, raw_xml: str) -> ParsedNFeEvent:
    # infEvento sob <evento> (dados da solicitação do autor)
    inf_evento = None
    ret_inf_evento = None

    for elem in root.iter():
        local_name = elem.tag.split('}')[-1]
        if local_name == "infEvento":
            if inf_evento is None:
                inf_evento = elem
            else:
                ret_inf_evento = elem

    access_key = _find_tag_text(root, "chNFe")
    event_code = _find_tag_text(root, "tpEvento")
    seq_str = _find_tag_text(root, "nSeqEvento")
    sequence = int(seq_str) if seq_str.isdigit() else 1

    dt_str = _find_tag_text(root, "dhEvento") or _find_tag_text(root, "dhRegEvento")
    event_datetime = _parse_iso_datetime(dt_str)

    desc_evento = _find_tag_text(root, "descEvento") or _find_tag_text(root, "xEvento")
    cancellation_reason = _find_tag_text(root, "xJust")
    correction_text = _find_tag_text(root, "xCorrecao")

    # Retorno da SEFAZ (<retEvento><infEvento>)
    protocol = ""
    sefaz_cstat = ""
    sefaz_reason = ""

    if ret_inf_evento is not None:
        protocol = _find_tag_text(ret_inf_evento, "nProt")
        sefaz_cstat = _find_tag_text(ret_inf_evento, "cStat")
        sefaz_reason = _find_tag_text(ret_inf_evento, "xMotivo")
    else:
        # Fallback no root
        protocol = _find_tag_text(root, "nProt")
        sefaz_cstat = _find_tag_text(root, "cStat")
        sefaz_reason = _find_tag_text(root, "xMotivo")

    return ParsedNFeEvent(
        access_key=access_key,
        event_code=event_code,
        event_description=desc_evento,
        sequence=sequence,
        event_datetime=event_datetime,
        protocol=protocol,
        sefaz_cstat=sefaz_cstat,
        sefaz_reason=sefaz_reason,
        cancellation_reason=cancellation_reason,
        correction_text=correction_text,
        raw_xml=raw_xml,
    )
