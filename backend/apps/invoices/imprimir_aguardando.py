"""A nota que ficou "aguardando autorização" também sai em contingência.

Na emissão, a ACBrLib já assina em tpEmis=9 a nota que a SEFAZ deixou
processando (`_transmitir_e_gravar`). Mas a nota que chegou a esse estado por
outro caminho — o comunicador caiu naquela hora, a consulta seguinte ainda
dizia "em processamento", nota de antes da contingência — ficava sem cupom: o
botão de imprimir recusava ("ainda não foi autorizada") e o PDV, consultando
em laço para imprimir, só ouvia "aguardando".

Quando alguém pede o cupom, a nota pendente NORMAL entra em contingência pela
mesma porta de sempre (`contingencia_offline.tentar`, com `para_imprimir`):
a chave normal é guardada e consultada antes de transmitir, e a autorizada
vence (`conferir_a_normal`).
"""
from django.db import transaction

from apps.invoices.models import Invoice
from apps.invoices.providers_erros import FiscalAmbiguous, FiscalUnavailable


def _erro_para(invoice):
    from apps.invoices.services import AWAITING_TRANSMISSION

    if (invoice.fiscal_payload or {}).get("awaiting") == AWAITING_TRANSMISSION:
        return FiscalUnavailable("A nota ainda não chegou à SEFAZ; cupom em contingência.")
    return FiscalAmbiguous("A SEFAZ ainda não autorizou a nota (aguardando autorização).")


def candidata(invoice):
    return (invoice.status == Invoice.STATUS_PENDING
            and invoice.emission_type == Invoice.EMISSION_NORMAL)


def assinar(invoice, config, provider, *, user=None):
    """Assina em contingência a nota já travada. True se entrou (falta o save)."""
    from apps.invoices import contingencia_offline

    if not candidata(invoice):
        return False
    return contingencia_offline.tentar(invoice, config, provider, _erro_para(invoice),
                                       user=user, para_imprimir=True)


def imprimivel(invoice, *, user=None):
    """`is_fiscally_printable`, depois de tentar a contingência na pendente.

    Atualiza `invoice` em memória com o que foi gravado.
    """
    from apps.core.tenant import tenant_context
    from apps.invoices.services import (
        _resolve_fiscal_config, em_voo_recente, get_provider, is_fiscally_printable,
    )

    if is_fiscally_printable(invoice) or not candidata(invoice):
        return is_fiscally_printable(invoice)
    with transaction.atomic(), tenant_context(invoice.account):
        travada = Invoice.all_objects.select_for_update().get(pk=invoice.pk)
        # Ainda transmitindo: a própria emissão decide (e assina, se preciso).
        if not em_voo_recente(travada):
            config = _resolve_fiscal_config(travada.restaurant, travada.branch)
            provider = get_provider(travada.provider or config.provider) if config else None
            if provider is not None and assinar(travada, config, provider, user=user):
                travada.save()
    invoice.refresh_from_db()
    return is_fiscally_printable(invoice)
