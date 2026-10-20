"""cStat 655: a Ciência (210210) chegou depois da manifestação final.

A SEFAZ recusa a Ciência quando a NF-e já tem Confirmação (210200),
Desconhecimento (210220) ou Operação não Realizada (210240) — feita por outro
sistema, outro CNPJ da rede ou pelo portal. Isso não é erro de quem manifesta:
a nota está manifestada. Reenviar o 210210 devolve 655 de novo para sempre, e
nSeqEvento=2 não muda nada (a regra é sobre o tipo do evento, não a sequência).

Por isso a nota não vai para "erro de manifestação": fica com "manifestação
final já existe", segue para buscar o XML completo e, se a distribuição já
trouxe o evento final, assume o estado dele.
"""
import logging

from apps.inbound_nfe.models import InboundNFe, NFeEvent

logger = logging.getLogger(__name__)

CSTAT_JA_TEM_FINAL = "655"

# tpEvento da manifestação final → estado da NF-e.
_ESTADO_DO_EVENTO = {
    "210200": InboundNFe.MANIFEST_CONFIRMED,
    "210220": InboundNFe.MANIFEST_UNKNOWN,
    "210240": InboundNFe.MANIFEST_NOT_PERFORMED,
}

ESTADOS_FINAIS = frozenset({InboundNFe.MANIFEST_FINAL_EXISTS, *_ESTADO_DO_EVENTO.values()})

MENSAGEM = "A NF-e já possui uma manifestação final registrada."

# O que o botão de Ciência devolve quando não há o que enviar: 200, e não 400,
# porque nada deu errado — a nota só não precisa mais de Ciência.
SEM_REENVIO = {
    "success": True,
    "science_sent": False,
    "reason": "final_manifestation_already_exists",
    "message": MENSAGEM,
}


def ja_tem_manifestacao_final(invoice) -> bool:
    return invoice.manifestation_status in ESTADOS_FINAIS


def tratar_ja_tem_final(invoice) -> tuple[bool, str]:
    """A resposta 655 de uma Ciência: marca a nota e vai buscar o que existe."""
    logger.warning(
        "Manifestação NF-e: cStat=655. Já existe manifestação final. chNFe=%s. "
        "Ciência não será reenviada.", invoice.access_key)

    invoice.manifestation_status = InboundNFe.MANIFEST_FINAL_EXISTS
    campos = ["manifestation_status"]
    if invoice.xml_status != InboundNFe.XML_STATUS_FULL_XML_AVAILABLE:
        invoice.xml_status = InboundNFe.XML_STATUS_FULL_XML_PENDING
        campos.append("xml_status")
    invoice.save(update_fields=campos)

    logger.info("Iniciando recuperação/reconciliação após 655: chNFe=%s", invoice.access_key)
    if invoice.xml_status != InboundNFe.XML_STATUS_FULL_XML_AVAILABLE:
        _buscar_o_xml_completo(invoice)
    reconciliar_manifestacao_final(invoice)
    return True, MENSAGEM


def _buscar_o_xml_completo(invoice) -> None:
    # Pelo módulo, e não por import do nome: é a mesma busca do fluxo 135.
    from apps.inbound_nfe.services import manifestation

    if manifestation.fetch_full_xml(invoice):
        return
    try:
        from apps.inbound_nfe.tasks import fetch_full_xml_task
        fetch_full_xml_task.delay(str(invoice.id))
    except Exception as exc:
        logger.warning("Não foi possível enfileirar fetch_full_xml_task após 655: %s", exc)


def reconciliar_manifestacao_final(invoice) -> None:
    """Assume o estado do evento final que a distribuição (resEvento ou
    procEventoNFe) já gravou para a chave. Sem evento, fica FINAL_EXISTS."""
    evento = (
        NFeEvent.all_objects
        .filter(account=invoice.account, access_key=invoice.access_key,
                event_code__in=_ESTADO_DO_EVENTO, sefaz_cstat__in=("", "135", "136"))
        .order_by("-event_datetime")
        .first()
    )
    if not evento:
        return
    invoice.manifestation_status = _ESTADO_DO_EVENTO[evento.event_code]
    invoice.save(update_fields=["manifestation_status"])
