"""Contingência OFFLINE da NFC-e (tpEmis=9): a SEFAZ não responde, a venda sai.

A contingência existia só no papel (`entrar_em_contingencia`): marcava a nota
e nunca produzia um documento de verdade, porque nenhum emissor sabia assinar
sem a SEFAZ. A ACBrLib sabe. Aqui se decide SE a nota entra — pela porta única,
que recusa tudo que não seja indisponibilidade — e ela é assinada com o mesmo
número, chave nova e `dhCont`/`xJust`. A transmissão é da retransmissão
periódica, que envia O MESMO XML (docs/FISCAL_ACBRLIB.md).
"""
import logging

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers_erros import FiscalProviderError

logger = logging.getLogger(__name__)


def permitida(config, provider):
    return (
        getattr(provider, "contingencia_offline", False)
        and config.offline_contingency
        and config.document_model == FiscalConfig.MODEL_NFCE
    )


def tentar(invoice, config, provider, erro, *, user=None):
    """Assina em contingência se o emissor sabe e a empresa permite. True se entrou."""
    from apps.invoices.services import entrar_em_contingencia

    if not permitida(config, provider):
        return False
    entrar_em_contingencia(invoice, erro, user=user)
    try:
        provider.emitir_em_contingencia(invoice, config, str(erro))
    except FiscalProviderError as falha:
        # Nem o comunicador assinou (ele também caiu): sem documento assinado
        # não há contingência — a nota volta a normal e espera a transmissão.
        logger.warning("Contingência não assinada para a nota %s: %s", invoice.pk, falha)
        invoice.emission_type = Invoice.EMISSION_NORMAL
        return False
    return True


def transmite_como_assinada(invoice):
    """A nota em contingência JÁ ASSINADA não pode ter chave nem dhEmi refeitos.

    O cupom foi impresso com aquela chave, e é aquele XML que a SEFAZ tem de
    receber. Refazer (`_refresh_emission_for_retry`) transmitiria outra nota.
    """
    return invoice.emission_type == Invoice.EMISSION_CONTINGENCY and bool(invoice.xml_content)
