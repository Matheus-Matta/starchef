"""Contingência OFFLINE da NFC-e (tpEmis=9): a SEFAZ não responde, a venda sai.

A contingência existia só no papel (`entrar_em_contingencia`): marcava a nota
e nunca produzia um documento de verdade, porque nenhum emissor sabia assinar
sem a SEFAZ. A ACBrLib sabe. Aqui se decide SE a nota entra — pela porta única,
que recusa tudo que não seja indisponibilidade — e ela é assinada com o mesmo
número, chave nova e `dhCont`/`xJust`. A transmissão é da retransmissão
periódica, que envia O MESMO XML (docs/FISCAL_ACBRLIB.md).

Na ACBrLib também entram a nota RECUSADA e a INCERTA (tempo esgotado,
"aguardando autorização"), para o cliente não sair sem cupom
(`contingency.imprime_em_contingencia`). A incerta guarda a chave da tentativa
normal (`chave_normal`), consultada antes de transmitir: se ela foi
autorizada, vale ela e a contingência é descartada (`conferir_a_normal`).
"""
import logging

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers_erros import (
    FiscalAmbiguous,
    FiscalNotFound,
    FiscalProviderError,
    FiscalRejection,
    FiscalUnavailable,
)

logger = logging.getLogger(__name__)


def permitida(config, provider):
    return (
        getattr(provider, "contingencia_offline", False)
        and config.offline_contingency
        and config.document_model == FiscalConfig.MODEL_NFCE
    )


def tentar(invoice, config, provider, erro, *, user=None, para_imprimir=False):
    """Assina em contingência se o emissor sabe e a empresa permite. True se entrou.

    `para_imprimir`: a recusa e a incerteza também entram (ver o topo).
    """
    from apps.invoices.services import entrar_em_contingencia

    if not permitida(config, provider):
        return False
    payload_antes = dict(invoice.fiscal_payload or {})
    chave_antes = invoice.access_key
    entrar_em_contingencia(invoice, erro, user=user, para_imprimir=para_imprimir)
    if isinstance(erro, FiscalAmbiguous) and chave_antes:
        # A normal pode existir na SEFAZ: é consultada antes da transmissão.
        invoice.fiscal_payload = {**invoice.fiscal_payload, "chave_normal": chave_antes}
    try:
        provider.emitir_em_contingencia(invoice, config, str(erro))
    except FiscalProviderError as falha:
        # Nem o comunicador assinou (ele também caiu): sem documento assinado
        # não há contingência — a nota volta a normal e espera a transmissão.
        logger.warning("Contingência não assinada para a nota %s: %s", invoice.pk, falha)
        invoice.emission_type = Invoice.EMISSION_NORMAL
        invoice.access_key = chave_antes
        invoice.fiscal_payload = payload_antes
        return False
    return True


def conferir_a_normal(invoice, provider, config):
    """Antes de transmitir a contingência, a tentativa normal foi autorizada?

    True quando foi: a nota passa a ser ELA (chave, protocolo) e a contingência
    é descartada — transmiti-la daria duplicidade. False quando a SEFAZ não a
    conhece (ou recusou): segue a transmissão da contingência. Indisponível,
    a falha sobe e a nota continua esperando.
    """
    payload = dict(invoice.fiscal_payload or {})
    chave_normal = payload.get("chave_normal")
    if not chave_normal or invoice.emission_type != Invoice.EMISSION_CONTINGENCY:
        return False
    contingencia = {campo: getattr(invoice, campo) for campo in (
        "access_key", "xml_content", "qr_code_data", "digest_value", "status", "error_message")}
    invoice.access_key = chave_normal
    try:
        provider.status(invoice)
    except (FiscalNotFound, FiscalRejection):
        for campo, valor in contingencia.items():
            setattr(invoice, campo, valor)
        payload.pop("chave_normal", None)
        invoice.fiscal_payload = payload
        return False
    except FiscalProviderError:
        for campo, valor in contingencia.items():
            setattr(invoice, campo, valor)
        raise
    if invoice.status != Invoice.STATUS_ISSUED:
        # Ainda processando: nem uma nem outra por enquanto. "Indisponível"
        # mantém a nota esperando a TRANSMISSÃO — a próxima rodada consulta de novo.
        for campo, valor in contingencia.items():
            setattr(invoice, campo, valor)
        raise FiscalUnavailable("A nota normal ainda está em processamento na SEFAZ.")
    novo = dict(invoice.fiscal_payload or {})
    novo.pop("chave_normal", None)
    novo["contingencia_descartada"] = contingencia["access_key"]
    invoice.fiscal_payload = novo
    invoice.emission_type = Invoice.EMISSION_NORMAL
    # XML, QR e digest guardados são os da contingência, não os desta chave.
    if invoice.xml_content == contingencia["xml_content"]:
        invoice.xml_content = ""
    invoice.digest_value = ""
    invoice.qr_code_data = _qr_da_normal(invoice, config)
    logger.info("Nota %s: a normal foi autorizada; contingência %s descartada.",
                invoice.pk, contingencia["access_key"])
    return True


def reemitir_normal_apos_recusa(invoice):
    """A contingência que a SEFAZ RECUSOU não é reenviada como está.

    O XML assinado é o que foi recusado: transmiti-lo de novo repete a recusa
    para sempre. Depois da correção, sai uma nota normal nova (mesmo número,
    chave refeita por `_refresh_emission_for_retry`).
    """
    if invoice.status == Invoice.STATUS_ERROR and invoice.emission_type == Invoice.EMISSION_CONTINGENCY:
        invoice.emission_type = Invoice.EMISSION_NORMAL
        invoice.xml_content = ""


def transmite_como_assinada(invoice):
    """A nota em contingência JÁ ASSINADA não pode ter chave nem dhEmi refeitos.

    O cupom foi impresso com aquela chave, e é aquele XML que a SEFAZ tem de
    receber. Refazer (`_refresh_emission_for_retry`) transmitiria outra nota.
    """
    return invoice.emission_type == Invoice.EMISSION_CONTINGENCY and bool(invoice.xml_content)


def _qr_da_normal(invoice, config):
    from apps.invoices.emission_secrets import segredos_de
    from apps.invoices.fiscal import build_nfce_qrcode

    segredos = segredos_de(config)
    return build_nfce_qrcode(access_key=invoice.access_key, environment=config.environment,
                             csc_id=segredos.csc_id, csc_token=segredos.csc_token,
                             base_url=config.qr_base_url)
